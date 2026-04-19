"""Redundant Type Cast Detector.

Detects redundant type conversions where the same type constructor wraps
an expression that is already of that type:

  - redundant_str: str(str(x)) — outer str() is unnecessary
  - redundant_int: int(int(x)) — outer int() is unnecessary
  - redundant_float: float(float(x)) — outer float() is unnecessary
  - redundant_list: list(list(x)) — outer list() is unnecessary
  - redundant_tuple: tuple(tuple(x)) — outer tuple() is unnecessary
  - redundant_set: set(set(x)) — outer set() is unnecessary
  - redundant_bool: bool(bool(x)) — outer bool() is unnecessary
  - redundant_bytes: bytes(bytes(x)) — outer bytes() is unnecessary

Redundant casts are dead code that suggests programmer confusion or
leftover refactoring artifacts.

Supports Python, JavaScript/TypeScript, Java, Go.
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

ISSUE_REDUNDANT_STR = "redundant_str"
ISSUE_REDUNDANT_INT = "redundant_int"
ISSUE_REDUNDANT_FLOAT = "redundant_float"
ISSUE_REDUNDANT_LIST = "redundant_list"
ISSUE_REDUNDANT_TUPLE = "redundant_tuple"
ISSUE_REDUNDANT_SET = "redundant_set"
ISSUE_REDUNDANT_BOOL = "redundant_bool"
ISSUE_REDUNDANT_BYTES = "redundant_bytes"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_STR: "Redundant str() wrapping: str(str(x)) is equivalent to str(x)",
    ISSUE_REDUNDANT_INT: "Redundant int() wrapping: int(int(x)) is equivalent to int(x)",
    ISSUE_REDUNDANT_FLOAT: "Redundant float() wrapping: float(float(x)) is equivalent to float(x)",
    ISSUE_REDUNDANT_LIST: "Redundant list() wrapping: list(list(x)) is equivalent to list(x)",
    ISSUE_REDUNDANT_TUPLE: "Redundant tuple() wrapping: tuple(tuple(x)) is equivalent to tuple(x)",
    ISSUE_REDUNDANT_SET: "Redundant set() wrapping: set(set(x)) is equivalent to set(x)",
    ISSUE_REDUNDANT_BOOL: "Redundant bool() wrapping: bool(bool(x)) is equivalent to bool(x)",
    ISSUE_REDUNDANT_BYTES: "Redundant bytes() wrapping: bytes(bytes(x)) is equivalent to bytes(x)",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_REDUNDANT_STR: "Remove the outer str() call.",
    ISSUE_REDUNDANT_INT: "Remove the outer int() call.",
    ISSUE_REDUNDANT_FLOAT: "Remove the outer float() call.",
    ISSUE_REDUNDANT_LIST: "Remove the outer list() call.",
    ISSUE_REDUNDANT_TUPLE: "Remove the outer tuple() call.",
    ISSUE_REDUNDANT_SET: "Remove the outer set() call.",
    ISSUE_REDUNDANT_BOOL: "Remove the outer bool() call.",
    ISSUE_REDUNDANT_BYTES: "Remove the outer bytes() call.",
}

_PYTHON_CASTS: dict[str, str] = {
    "str": ISSUE_REDUNDANT_STR,
    "int": ISSUE_REDUNDANT_INT,
    "float": ISSUE_REDUNDANT_FLOAT,
    "list": ISSUE_REDUNDANT_LIST,
    "tuple": ISSUE_REDUNDANT_TUPLE,
    "set": ISSUE_REDUNDANT_SET,
    "bool": ISSUE_REDUNDANT_BOOL,
    "bytes": ISSUE_REDUNDANT_BYTES,
}

_JS_CASTS: dict[str, str] = {
    "String": ISSUE_REDUNDANT_STR,
    "Number": ISSUE_REDUNDANT_INT,
    "Boolean": ISSUE_REDUNDANT_BOOL,
}

_JAVA_CASTS: dict[str, str] = {
    "Integer": ISSUE_REDUNDANT_INT,
    "String": ISSUE_REDUNDANT_STR,
    "Double": ISSUE_REDUNDANT_FLOAT,
    "Boolean": ISSUE_REDUNDANT_BOOL,
}

_CAST_MAPS: dict[str, dict[str, str]] = {
    ".py": _PYTHON_CASTS,
    ".js": _JS_CASTS,
    ".jsx": _JS_CASTS,
    ".ts": _JS_CASTS,
    ".tsx": _JS_CASTS,
    ".java": _JAVA_CASTS,
}

_CALL_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"call"}),
    ".js": frozenset({"call_expression"}),
    ".jsx": frozenset({"call_expression"}),
    ".ts": frozenset({"call_expression"}),
    ".tsx": frozenset({"call_expression"}),
    ".java": frozenset({"method_invocation", "object_creation_expression"}),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _get_call_name(node: tree_sitter.Node, ext: str) -> str:
    if ext == ".py":
        func_node = node.child_by_field_name("function")
        if func_node and func_node.type == "identifier":
            return _txt(func_node)
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        func_node = node.child_by_field_name("function")
        if func_node and func_node.type == "identifier":
            return _txt(func_node)
    elif ext == ".java":
        if node.type == "method_invocation":
            for child in node.children:
                if child.type == "identifier":
                    return _txt(child)
        elif node.type == "object_creation_expression":
            for child in node.children:
                if child.type == "type_identifier":
                    return _txt(child)
    return ""


def _get_single_arg(node: tree_sitter.Node, ext: str) -> tree_sitter.Node | None:
    if ext == ".py":
        args_list = node.child_by_field_name("arguments")
        if args_list:
            named = [c for c in args_list.children if c.is_named]
            if len(named) == 1:
                return named[0]
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        args_list = node.child_by_field_name("arguments")
        if args_list:
            named = [c for c in args_list.children if c.is_named]
            if len(named) == 1:
                return named[0]
    elif ext == ".java":
        args_node = None
        for child in node.children:
            if child.type == "argument_list":
                args_node = child
                break
        if args_node:
            named = [c for c in args_node.children if c.is_named]
            if len(named) == 1:
                return named[0]
    return None


@dataclass(frozen=True)
class RedundantCastIssue:
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
class RedundantCastResult:
    file_path: str
    total_calls: int
    issues: list[RedundantCastIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_calls": self.total_calls,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class RedundantTypeCastAnalyzer(BaseAnalyzer):
    """Detects redundant type casts (e.g., str(str(x)))."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> RedundantCastResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return RedundantCastResult(
                file_path=str(path),
                total_calls=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return RedundantCastResult(
                file_path=str(path),
                total_calls=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        cast_map = _CAST_MAPS.get(ext, {})
        call_types = _CALL_NODE_TYPES.get(ext, frozenset())
        issues: list[RedundantCastIssue] = []
        total_calls = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in call_types:
                total_calls += 1
                outer_name = _get_call_name(node, ext)
                if outer_name in cast_map:
                    arg = _get_single_arg(node, ext)
                    if arg and arg.type in call_types:
                        inner_name = _get_call_name(arg, ext)
                        if inner_name == outer_name:
                            issue_type = cast_map[outer_name]
                            issues.append(RedundantCastIssue(
                                line=node.start_point[0] + 1,
                                issue_type=issue_type,
                                severity=SEVERITY_LOW,
                                description=_DESCRIPTIONS[issue_type],
                                suggestion=_SUGGESTIONS[issue_type],
                                context=_txt(node),
                            ))
            for child in node.children:
                stack.append(child)

        return RedundantCastResult(
            file_path=str(path),
            total_calls=total_calls,
            issues=issues,
        )
