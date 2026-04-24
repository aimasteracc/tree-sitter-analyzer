"""Abstraction Level Mixing Detector.

Detects functions that mix high-level abstractions (named function calls)
with low-level implementation details (raw string ops, arithmetic, indexing).
This violates the Clean Code principle: "Functions should operate at one
level of abstraction" (Robert C. Martin).

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_MIXED_ABSTRACTION = "mixed_abstraction"
ISSUE_LEAKY_ABSTRACTION = "leaky_abstraction"

MIN_STATEMENTS = 6
MIN_HIGH_LEVEL = 3
MIN_LOW_LEVEL = 3
MIN_LEAKY_HIGH = 2
MIN_LEAKY_LOW = 2

_LOW_LEVEL_METHODS: frozenset[str] = frozenset({
    "split", "join", "strip", "lstrip", "rstrip",
    "trim", "trimLeft", "trimRight", "trimStart", "trimEnd",
    "TrimSpace", "TrimLeft", "TrimRight", "TrimPrefix", "TrimSuffix",
    "lower", "upper", "capitalize", "title", "swapcase", "casefold",
    "toLowerCase", "toUpperCase", "toLocaleLowerCase", "toLocaleUpperCase",
    "ToLower", "ToUpper", "ToTitle",
    "encode", "decode", "replace", "substring", "slice", "substr",
    "Replace", "ReplaceAll",
    "parseInt", "parseFloat", "Number", "String",
    "append", "push", "pop", "shift", "unshift",
    "Append", "Copy", "Clone",
    "keys", "values", "items", "entries",
    "toString", "valueOf",
    "charAt", "charCodeAt", "codePointAt", "indexOf", "lastIndexOf",
    "startsWith", "endsWith", "includes", "contains",
    "Atoi", "Itoa", "Sprintf", "Printf", "FormatInt", "FormatFloat",
    "HasPrefix", "HasSuffix", "Contains", "Index", "Count",
    "Split", "SplitN", "Join", "Fields", "Repeat", "Title",
})

_LOW_LEVEL_TYPES: frozenset[str] = frozenset({
    "int", "float", "str", "bool", "bytes", "bytearray",
    "list", "dict", "set", "tuple", "frozenset",
    "len", "range", "enumerate", "zip", "map", "filter",
    "sorted", "reversed", "sum", "min", "max", "abs", "round",
    "type", "isinstance", "issubclass",
    "make", "new", "cap",
})

_ARITH_OPS: frozenset[str] = frozenset({
    "+", "-", "*", "/", "%", "//", "**",
    "&", "|", "^", "<<", ">>",
    "+=", "-=", "*=", "/=", "%=",
})

_FUNCTION_NODE_TYPES: frozenset[str] = frozenset({
    "function_definition", "method_definition",
    "function_declaration", "method_declaration",
    "method_declaration_statement",
    "arrow_function", "function_expression",
    "function",
})

_CONSTRUCTOR_NAMES: frozenset[str] = frozenset({
    "__init__", "constructor", "<init>",
})

_TEST_FUNC_PATTERNS: frozenset[str] = frozenset({
    "test_", "Test", "it(", "describe(",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _extract_call_names(node: tree_sitter.Node) -> list[str]:
    names: list[str] = []
    _walk_calls(node, names)
    return names


def _walk_calls(node: tree_sitter.Node, names: list[str]) -> None:
    if node.type in ("call_expression", "call", "method_invocation"):
        func_node = node.child_by_field_name("function") or node.child_by_field_name("name")
        if func_node:
            name = _txt(func_node)
            if "." in name:
                name = name.rsplit(".", 1)[-1]
            names.append(name)
    for child in node.children:
        _walk_calls(child, names)


def _has_arithmetic(node: tree_sitter.Node) -> bool:
    for child in node.children:
        if child.type in ("binary_operator", "augmented_assignment"):
            op_node = child.child_by_field_name("operator")
            if op_node and _txt(op_node) in _ARITH_OPS:
                return True
        if _has_arithmetic(child):
            return True
    return False


def _has_indexing(node: tree_sitter.Node) -> bool:
    for child in node.children:
        if child.type == "subscript":
            return True
        if _has_indexing(child):
            return True
    return False


def _is_low_level_stmt(node: tree_sitter.Node) -> bool:
    call_names = _extract_call_names(node)
    low_calls = [n for n in call_names if n in _LOW_LEVEL_METHODS or n in _LOW_LEVEL_TYPES]
    if low_calls and len(low_calls) == len(call_names):
        return True
    if not call_names:
        if _has_arithmetic(node) or _has_indexing(node):
            return True
    return False


def _is_high_level_stmt(node: tree_sitter.Node) -> bool:
    call_names = _extract_call_names(node)
    if not call_names:
        return False
    high_calls = [n for n in call_names if n not in _LOW_LEVEL_METHODS and n not in _LOW_LEVEL_TYPES]
    return len(high_calls) > 0


def _count_levels(body_node: tree_sitter.Node) -> tuple[int, int, int]:
    high = 0
    low = 0
    transitions = 0
    last_level: str | None = None

    for child in body_node.children:
        if child.type in ("comment", "block_comment", "line_comment",
                          "pass_statement", "return_statement", "throw_statement",
                          "break_statement", "continue_statement"):
            continue

        is_high = _is_high_level_stmt(child)
        is_low = _is_low_level_stmt(child)

        if is_high and not is_low:
            current = "high"
            high += 1
        elif is_low:
            current = "low"
            low += 1
        else:
            current = last_level if last_level is not None else "neutral"

        if last_level is not None and current != last_level:
            transitions += 1
        last_level = current

    return high, low, transitions


@dataclass(frozen=True)
class AbstractionIssue:
    line_number: int
    function_name: str
    issue_type: str
    severity: str
    high_level_count: int
    low_level_count: int
    transitions: int


@dataclass(frozen=True)
class AbstractionResult:
    file_path: str
    total_functions: int
    issues: tuple[AbstractionIssue, ...]


class AbstractionLevelAnalyzer(BaseAnalyzer):
    """Detects functions mixing high-level and low-level abstractions."""

    def analyze_file(self, file_path: Path) -> AbstractionResult:
        source = file_path.read_bytes()
        ext = file_path.suffix.lower()
        lang = self._detect_language(ext)
        if lang is None:
            return AbstractionResult(
                file_path=str(file_path),
                total_functions=0,
                issues=(),
            )

        tree = self._parse(source, ext)
        if tree is None:
            return AbstractionResult(
                file_path=str(file_path),
                total_functions=0,
                issues=(),
            )

        root = tree.root_node
        functions = self._find_functions(root, lang)
        issues: list[AbstractionIssue] = []

        for func_node, func_name in functions:
            if self._should_skip(func_name):
                continue
            body = self._get_body(func_node, lang)
            if body is None:
                continue

            child_count = len([c for c in body.children
                               if c.type not in ("comment", "block_comment",
                                                 "line_comment", "{", "}")])
            if child_count < MIN_STATEMENTS:
                continue

            high, low, transitions = _count_levels(body)
            issue = self._evaluate(func_node, func_name, high, low, transitions)
            if issue is not None:
                issues.append(issue)

        return AbstractionResult(
            file_path=str(file_path),
            total_functions=len(functions),
            issues=tuple(issues),
        )

    def _detect_language(self, ext: str) -> str | None:
        mapping: dict[str, str] = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
        }
        return mapping.get(ext)

    def _parse(self, source: bytes, ext: str) -> tree_sitter.Tree | None:
        try:
            _, parser = self._get_parser(ext)
            if parser is None:
                return None
            result = parser.parse(source)
            return result if result is not None else None
        except Exception:
            logger.debug("Failed to parse for extension %s", ext)
            return None

    def _find_functions(
        self, node: tree_sitter.Node, lang: str,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        self._walk_for_functions(node, results, lang)
        return results

    def _walk_for_functions(
        self, node: tree_sitter.Node,
        results: list[tuple[tree_sitter.Node, str]],
        lang: str,
    ) -> None:
        func_type = node.type

        if func_type in _FUNCTION_NODE_TYPES:
            name = self._get_func_name(node, lang)
            if name:
                results.append((node, name))

        for child in node.children:
            self._walk_for_functions(child, results, lang)

    def _get_func_name(self, node: tree_sitter.Node, lang: str) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return _txt(name_node)

        if lang in ("javascript", "typescript"):
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                name_node = parent.child_by_field_name("name")
                if name_node:
                    return _txt(name_node)
            if parent and parent.type in ("assignment_expression", "property_definition"):
                left = parent.child_by_field_name("left")
                if left:
                    return _txt(left)

        if lang == "go" and node.type == "function":
            for child in node.children:
                if child.type == "identifier":
                    return _txt(child)

        return ""

    def _should_skip(self, func_name: str) -> bool:
        if func_name in _CONSTRUCTOR_NAMES:
            return True
        for pattern in _TEST_FUNC_PATTERNS:
            if pattern in func_name:
                return True
        return False

    def _get_body(self, node: tree_sitter.Node, lang: str) -> tree_sitter.Node | None:
        body = node.child_by_field_name("body")
        if body:
            return body

        if lang in ("javascript", "typescript"):
            for child in node.children:
                if child.type in ("statement_block", "compound_statement"):
                    return child

        if lang == "go":
            for child in node.children:
                if child.type == "block":
                    return child

        if lang == "java":
            for child in node.children:
                if child.type == "block" or child.type == "constructor_body":
                    return child

        return None

    def _evaluate(
        self,
        func_node: tree_sitter.Node,
        func_name: str,
        high: int,
        low: int,
        transitions: int,
    ) -> AbstractionIssue | None:
        if high >= MIN_HIGH_LEVEL and low >= MIN_LOW_LEVEL:
            return AbstractionIssue(
                line_number=func_node.start_point[0] + 1,
                function_name=func_name,
                issue_type=ISSUE_MIXED_ABSTRACTION,
                severity=SEVERITY_MEDIUM,
                high_level_count=high,
                low_level_count=low,
                transitions=transitions,
            )

        if high >= MIN_LEAKY_HIGH and low >= MIN_LEAKY_LOW and transitions >= 1:
            return AbstractionIssue(
                line_number=func_node.start_point[0] + 1,
                function_name=func_name,
                issue_type=ISSUE_LEAKY_ABSTRACTION,
                severity=SEVERITY_LOW,
                high_level_count=high,
                low_level_count=low,
                transitions=transitions,
            )

        return None
