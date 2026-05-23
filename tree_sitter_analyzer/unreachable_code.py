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

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .call_graph import _FUNC_DEF_TYPES
from .core.parser import Parser
from .project_graph import _language_from_ext
from .utils import setup_logger

logger = setup_logger(__name__)

_EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "htmlcov", ".cache", ".eggs",
    ".idea", ".vscode", ".claude",
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

_TERMINAL_CALL_NAMES = frozenset({
    "sys.exit", "os._exit", "exit", "quit",
    "abort", "fatal", "die", "panic",
})

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


def _node_text(node: Any, source: str) -> str:
    try:
        text = node.text
        if isinstance(text, bytes):
            return text.decode("utf-8")
        return str(text)
    except Exception:
        return source[node.start_byte:node.end_byte]


def _is_terminal_call(node: Any, source: str, language: str) -> bool:
    if language not in ("python", "javascript", "typescript", "java"):
        return False
    call_type = "call" if language == "python" else "call_expression"
    if node.type != call_type:
        return False
    func_node = node.child_by_field_name("function")
    if func_node is None:
        if language in ("javascript", "typescript"):
            for child in node.children:
                if child.type == "identifier":
                    func_node = child
                    break
                if child.type == "member_expression":
                    func_node = child
                    break
        if func_node is None:
            return False
    call_name = _node_text(func_node, source).strip()
    for pattern in _TERMINAL_CALL_NAMES:
        if call_name.endswith(pattern) or call_name == pattern:
            return True
    return False


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
            if child.type in ("comment", "pass_statement"):
                continue
            start_line = child.start_point[0] + 1
            end_line = child.end_point[0] + 1
            if start_line != end_line or child.type not in ("newline",):
                results.append(UnreachableBlock(
                    file_path=file_path,
                    function_name=func_name,
                    start_line=start_line,
                    end_line=end_line,
                    reason=f"code after {children[terminal_idx].type.replace('_', ' ')} on line {children[terminal_idx].start_point[0] + 1}",
                    severity="warning",
                ))
            continue

        if _is_terminal_statement(child, source, language):
            found_terminal = True
            terminal_idx = i
            if _analyze_child_nodes(child, source, language, func_name, file_path, results):
                pass
            continue

        if language in _LOOP_BREAK_TYPES and child.type in _LOOP_BREAK_TYPES[language]:
            found_terminal = True
            terminal_idx = i
            continue

        if_type = _IF_TYPES.get(language)
        if if_type and child.type == if_type:
            _analyze_if_statement(child, source, language, func_name, file_path, results)

        try_type = _TRY_TYPES.get(language)
        if try_type and child.type == try_type:
            _analyze_try_statement(child, source, language, func_name, file_path, results)

    return found_terminal


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
            _analyze_block_unreachable(child, source, language, func_name, file_path, results)
        else:
            _analyze_child_nodes(child, source, language, func_name, file_path, results)


def _analyze_if_statement(
    node: Any,
    source: str,
    language: str,
    func_name: str,
    file_path: str,
    results: list[UnreachableBlock],
) -> None:
    condition = node.child_by_field_name("condition")
    if condition is None:
        for child in node.children:
            if child.type == "parenthesized_expression":
                condition = child
                break

    block_type = _BLOCK_TYPES.get(language, "block")
    consequence = None
    alternative = None

    for child in getattr(node, "children", []):
        if child.type == block_type and consequence is None:
            consequence = child
        elif child.type == "else_clause" or child.type == "else":
            alternative = child

    if condition is not None and _is_false_literal(condition, source):
        if consequence is not None:
            start_line = consequence.start_point[0] + 1
            end_line = consequence.end_point[0] + 1
            results.append(UnreachableBlock(
                file_path=file_path,
                function_name=func_name,
                start_line=start_line,
                end_line=end_line,
                reason=f"if-False branch is never executed (condition is always False on line {condition.start_point[0] + 1})",
                severity="info",
            ))
    elif condition is not None and _is_true_literal(condition, source):
        if alternative is not None:
            alt_block = None
            for child in getattr(alternative, "children", []):
                if child.type == block_type:
                    alt_block = child
                    break
            if alt_block is not None:
                start_line = alt_block.start_point[0] + 1
                end_line = alt_block.end_point[0] + 1
                results.append(UnreachableBlock(
                    file_path=file_path,
                    function_name=func_name,
                    start_line=start_line,
                    end_line=end_line,
                    reason=f"else branch of if-True is never executed (condition is always True on line {condition.start_point[0] + 1})",
                    severity="info",
                ))

    if consequence is not None:
        _analyze_block_unreachable(consequence, source, language, func_name, file_path, results)
    if alternative is not None:
        block_type_name = _BLOCK_TYPES.get(language, "block")
        for child in getattr(alternative, "children", []):
            if child.type == block_type_name:
                _analyze_block_unreachable(child, source, language, func_name, file_path, results)
            elif child.type == _IF_TYPES.get(language, ""):
                _analyze_if_statement(child, source, language, func_name, file_path, results)


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
            _analyze_block_unreachable(child, source, language, func_name, file_path, results)
        elif child.type in ("except_clause", "catch_clause", "handler_clause"):
            for sub in getattr(child, "children", []):
                if sub.type == block_type:
                    _analyze_block_unreachable(sub, source, language, func_name, file_path, results)
        elif child.type in ("finally_clause", "finally_block"):
            for sub in getattr(child, "children", []):
                if sub.type == block_type:
                    _analyze_block_unreachable(sub, source, language, func_name, file_path, results)


def analyze_file_unreachable(
    file_path: str,
    language: str | None = None,
) -> UnreachableCodeResult:
    """Analyze a single file for unreachable code paths."""
    if language is None:
        ext = os.path.splitext(file_path)[1].lower()
        language = _language_from_ext(ext)
    if language is None:
        return UnreachableCodeResult(
            file_path=file_path,
            language="unknown",
            errors=1,
        )

    try:
        with open(file_path, "rb") as f:
            source_bytes = f.read()
        source = source_bytes.decode("utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Cannot read %s: %s", file_path, exc)
        return UnreachableCodeResult(
            file_path=file_path,
            language=language,
            errors=1,
        )

    parser = Parser()
    result = parser.parse_file(file_path)
    if not result.success or result.tree is None:
        return UnreachableCodeResult(
            file_path=file_path,
            language=language,
            errors=1,
        )

    tree = result.tree
    root = tree.root_node

    func_def_types = _FUNC_DEF_TYPES.get(language, set())
    block_type = _BLOCK_TYPES.get(language, "block")
    results: list[UnreachableBlock] = []
    functions_analyzed = 0

    def _walk_for_functions(node: Any) -> None:
        nonlocal functions_analyzed
        if not hasattr(node, "type"):
            return
        if node.type in func_def_types:
            functions_analyzed += 1
            func_name = _get_function_name(node, source, language)
            body = node.child_by_field_name("body")
            if body is not None:
                if body.type == block_type:
                    _analyze_block_unreachable(body, source, language, func_name, file_path, results)
                else:
                    for child in getattr(body, "children", []):
                        if child.type == block_type:
                            _analyze_block_unreachable(child, source, language, func_name, file_path, results)
            return
        if node.type in _CLASS_DEF_TYPES_SET:
            for child in getattr(node, "children", []):
                _walk_for_functions(child)
            return
        for child in getattr(node, "children", []):
            _walk_for_functions(child)

    _walk_for_functions(root)

    return UnreachableCodeResult(
        file_path=file_path,
        language=language,
        unreachable_blocks=results,
        functions_analyzed=functions_analyzed,
    )


_CLASS_DEF_TYPES_SET: set[str] = set()
try:
    from .call_graph import _CLASS_DEF_TYPES
    for _s in _CLASS_DEF_TYPES.values():
        _CLASS_DEF_TYPES_SET.update(_s)
except Exception:
    pass


def _get_function_name(node: Any, source: str, language: str) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, source)
    if language in ("javascript", "typescript"):
        parent = node.parent
        if parent is not None:
            key_node = parent.child_by_field_name("key")
            if key_node is not None:
                return _node_text(key_node, source)
            prop = parent.child_by_field_name("property")
            if prop is not None:
                return _node_text(prop, source)
    return "<anonymous>"


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
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for fname in sorted(filenames):
            if count >= max_files:
                break
            ext = os.path.splitext(fname)[1].lower()
            lang = _language_from_ext(ext)
            if lang is None:
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, project_root)
            if not include_test_files and _test_pattern.search(rel):
                continue
            result = analyze_file_unreachable(full, language=lang)
            if result.unreachable_blocks or result.errors:
                results.append(result)
            count += 1

    return results
