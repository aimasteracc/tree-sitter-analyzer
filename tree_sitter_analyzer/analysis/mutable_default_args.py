"""Mutable Default Arguments Detector.

Detects Python functions with mutable default arguments — one of the most
common Python bugs. Mutable objects like lists, dicts, and sets as default
parameter values are shared across all calls, causing unexpected behavior.
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

_MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset({
    "list", "dict", "set", "bytearray",
})

_MUTABLE_LITERALS: frozenset[str] = frozenset({
    "list", "dictionary", "set",
})


@dataclass(frozen=True)
class MutableDefaultArg:
    """A parameter with a mutable default value."""

    line_number: int
    function_name: str
    parameter_name: str
    default_type: str
    severity: str


@dataclass(frozen=True)
class MutableDefaultArgsResult:
    """Aggregated result for mutable default args detection."""

    total_functions: int
    violation_count: int
    violations: tuple[MutableDefaultArg, ...]
    file_path: str

    @property
    def is_clean(self) -> bool:
        return self.violation_count == 0


class MutableDefaultArgsAnalyzer(BaseAnalyzer):
    """Detects mutable default arguments in Python functions."""

    SUPPORTED_EXTENSIONS: set[str] = {".py"}

    def analyze_file(self, file_path: Path | str) -> MutableDefaultArgsResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return MutableDefaultArgsResult(
                total_functions=0,
                violation_count=0,
                violations=(),
                file_path=str(path),
            )
        path, ext = check
        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> MutableDefaultArgsResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return MutableDefaultArgsResult(
                total_functions=0,
                violation_count=0,
                violations=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        violations: list[MutableDefaultArg] = []

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total
            if node.type in ("function_definition", "class_definition"):
                total += 1

            if node.type == "default_parameter":
                self._check_parameter(
                    node, content, violations,
                )

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return MutableDefaultArgsResult(
            total_functions=total,
            violation_count=len(violations),
            violations=tuple(violations),
            file_path=str(path),
        )

    def _check_parameter(
        self,
        node: tree_sitter.Node,
        content: bytes,
        violations: list[MutableDefaultArg],
    ) -> None:
        param_name = self._get_param_name(node, content)
        func_name = self._get_parent_function_name(node, content)
        default_value = node.child_by_field_name("value")
        if default_value is None:
            return

        default_type, severity = self._classify_default(default_value, content)
        if default_type is not None:
            violations.append(MutableDefaultArg(
                line_number=node.start_point[0] + 1,
                function_name=func_name,
                parameter_name=param_name,
                default_type=default_type,
                severity=severity,
            ))

    def _classify_default(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> tuple[str | None, str]:
        if node.type == "list":
            return "list", SEVERITY_HIGH
        if node.type == "dictionary":
            return "dict", SEVERITY_HIGH
        if node.type == "set":
            return "set", SEVERITY_HIGH

        if node.type == "call":
            func = node.child_by_field_name("function")
            if func is not None:
                name = content[func.start_byte:func.end_byte].decode(
                    "utf-8", errors="replace",
                )
                if name in _MUTABLE_CONSTRUCTORS:
                    return name, SEVERITY_HIGH
                if name == "frozenset":
                    return None, SEVERITY_LOW
                if name in ("tuple", "str", "int", "float", "bool",
                            "bytes", "complex", "range", "type", "NoneType"):
                    return None, SEVERITY_LOW

        if node.type == "list_comprehension":
            return "list_comprehension", SEVERITY_HIGH
        if node.type == "set_comprehension":
            return "set_comprehension", SEVERITY_HIGH
        if node.type == "dictionary_comprehension":
            return "dict_comprehension", SEVERITY_HIGH

        if node.type == "identifier":
            text = content[node.start_byte:node.end_byte].decode(
                "utf-8", errors="replace",
            )
            if text in ("True", "False", "None"):
                return None, SEVERITY_LOW
            return text, SEVERITY_MEDIUM

        return None, SEVERITY_LOW

    def _get_param_name(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace",
            )
        for child in node.children:
            if child.type == "identifier":
                return content[child.start_byte:child.end_byte].decode(
                    "utf-8", errors="replace",
                )
        return "<unknown>"

    def _get_parent_function_name(
        self,
        node: tree_sitter.Node,
        content: bytes,
    ) -> str:
        current = node.parent
        while current is not None:
            if current.type in ("function_definition", "class_definition"):
                for child in current.children:
                    if child.type == "identifier":
                        return content[
                            child.start_byte:child.end_byte
                        ].decode("utf-8", errors="replace")
                name = current.child_by_field_name("name")
                if name is not None:
                    return content[name.start_byte:name.end_byte].decode(
                        "utf-8", errors="replace",
                    )
                return "<anonymous>"
            current = current.parent
        return "<module>"
