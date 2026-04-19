"""Builtin Shadow Detector.

Detects variable, function, class, and parameter names that shadow
Python builtins:

  - shadowed_builtin: assignment `list = [...]` shadows the list builtin
  - shadowed_by_function: def id() shadows the id() builtin
  - shadowed_by_class: class type shadows the type() builtin
  - shadowed_by_parameter: def foo(list) shadows the list builtin
  - shadowed_by_import: from x import list shadows the list builtin
  - shadowed_by_for_target: for list in items shadows the list builtin

Shadowing builtins silently breaks all subsequent calls to the original
builtin. This is Pylint W0622 and a common source of confusing bugs.

Supports Python only (other languages don't have the same problem).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_SHADOWED_ASSIGNMENT = "shadowed_builtin"
ISSUE_SHADOWED_FUNCTION = "shadowed_by_function"
ISSUE_SHADOWED_CLASS = "shadowed_by_class"
ISSUE_SHADOWED_PARAMETER = "shadowed_by_parameter"
ISSUE_SHADOWED_IMPORT = "shadowed_by_import"
ISSUE_SHADOWED_FOR_TARGET = "shadowed_by_for_target"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_SHADOWED_ASSIGNMENT: SEVERITY_HIGH,
    ISSUE_SHADOWED_FUNCTION: SEVERITY_HIGH,
    ISSUE_SHADOWED_CLASS: SEVERITY_HIGH,
    ISSUE_SHADOWED_PARAMETER: SEVERITY_MEDIUM,
    ISSUE_SHADOWED_IMPORT: SEVERITY_HIGH,
    ISSUE_SHADOWED_FOR_TARGET: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_SHADOWED_ASSIGNMENT: (
        "Assignment shadows builtin '{name}': subsequent calls to "
        "{name}() will use this variable instead"
    ),
    ISSUE_SHADOWED_FUNCTION: (
        "Function definition shadows builtin '{name}': "
        "calling {name}() will call this function instead"
    ),
    ISSUE_SHADOWED_CLASS: (
        "Class definition shadows builtin '{name}': "
        "using {name}() will construct this class instead"
    ),
    ISSUE_SHADOWED_PARAMETER: (
        "Parameter shadows builtin '{name}': "
        "using {name} inside the function refers to this parameter"
    ),
    ISSUE_SHADOWED_IMPORT: (
        "Import shadows builtin '{name}': "
        "subsequent calls to {name}() will use the imported name"
    ),
    ISSUE_SHADOWED_FOR_TARGET: (
        "For-loop target shadows builtin '{name}': "
        "using {name} in the loop body refers to loop variable"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_SHADOWED_ASSIGNMENT: "Rename the variable to avoid shadowing the builtin.",
    ISSUE_SHADOWED_FUNCTION: "Rename the function to avoid shadowing the builtin.",
    ISSUE_SHADOWED_CLASS: "Rename the class to avoid shadowing the builtin.",
    ISSUE_SHADOWED_PARAMETER: "Rename the parameter to avoid shadowing the builtin.",
    ISSUE_SHADOWED_IMPORT: "Use explicit import: 'from x import list as x_list'.",
    ISSUE_SHADOWED_FOR_TARGET: "Rename the loop variable to avoid shadowing the builtin.",
}

PYTHON_BUILTINS: frozenset[str] = frozenset({
    "ArithmeticError", "AssertionError", "AttributeError",
    "BaseException", "BlockingIOError", "BrokenPipeError",
    "BufferError", "BytesWarning", "ChildProcessError",
    "ConnectionAbortedError", "ConnectionError",
    "ConnectionRefusedError", "ConnectionResetError",
    "DeprecationWarning", "EOFError", "EnvironmentError",
    "Exception", "FileExistsError", "FileNotFoundError",
    "FloatingPointError", "FutureWarning", "GeneratorExit",
    "IOError", "ImportError", "ImportWarning",
    "IndentationError", "IndexError", "InterruptedError",
    "IsADirectoryError", "KeyError", "KeyboardInterrupt",
    "LookupError", "MemoryError", "ModuleNotFoundError",
    "NameError", "NotADirectoryError", "NotImplementedError",
    "OSError", "OverflowError", "PendingDeprecationWarning",
    "PermissionError", "ProcessLookupError", "RecursionError",
    "ReferenceError", "ResourceWarning", "RuntimeError",
    "RuntimeWarning", "StopAsyncIteration", "StopIteration",
    "SyntaxError", "SyntaxWarning", "SystemError",
    "SystemExit", "TabError", "TimeoutError",
    "TypeError", "UnboundLocalError", "UnicodeDecodeError",
    "UnicodeEncodeError", "UnicodeError", "UnicodeWarning",
    "UserWarning", "ValueError", "Warning",
    "ZeroDivisionError",
    "__build_class__", "__debug__", "__import__",
    "abs", "aiter", "all", "anext", "any",
    "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile",
    "complex", "copyright", "credits", "delattr", "dict",
    "dir", "divmod", "enumerate", "eval", "exec",
    "exit", "filter", "float", "format", "frozenset",
    "getattr", "globals", "hasattr", "hash", "help",
    "hex", "id", "input", "int", "isinstance",
    "issubclass", "iter", "len", "license", "list",
    "locals", "map", "max", "memoryview", "min",
    "next", "object", "oct", "open", "ord",
    "pow", "print", "property", "quit", "range",
    "repr", "reversed", "round", "set", "setattr",
    "slice", "sorted", "staticmethod", "str", "sum",
    "super", "tuple", "type", "vars", "zip",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _get_name(node: tree_sitter.Node) -> str:
    for child in node.children:
        if child.is_named and child.type == "identifier":
            return _txt(child)
    return ""


def _check_dotted_name(node: tree_sitter.Node) -> str | None:
    if node.type == "dotted_name":
        parts: list[str] = []
        for child in node.children:
            if child.type == "identifier":
                parts.append(_txt(child))
        return ".".join(parts) if parts else None
    return None


@dataclass(frozen=True)
class BuiltinShadowIssue:
    line: int
    issue_type: str
    severity: str
    name: str
    description: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "name": self.name,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class BuiltinShadowResult:
    file_path: str
    total_definitions: int
    issues: list[BuiltinShadowIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_definitions": self.total_definitions,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class BuiltinShadowAnalyzer(BaseAnalyzer):
    """Detects names that shadow Python builtins."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {".py"}

    def analyze_file(
        self, file_path: str | Path,
    ) -> BuiltinShadowResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return BuiltinShadowResult(
                file_path=str(path),
                total_definitions=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return BuiltinShadowResult(
                file_path=str(path),
                total_definitions=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        issues: list[BuiltinShadowIssue] = []
        total_defs = 0

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            total_defs += self._check_node(node, issues)
            for child in node.children:
                stack.append(child)

        return BuiltinShadowResult(
            file_path=str(path),
            total_definitions=total_defs,
            issues=issues,
        )

    def _make_issue(
        self, issue_type: str, name: str, line: int,
    ) -> BuiltinShadowIssue:
        return BuiltinShadowIssue(
            line=line,
            issue_type=issue_type,
            severity=_SEVERITY_MAP[issue_type],
            name=name,
            description=_DESCRIPTIONS[issue_type].format(name=name),
            suggestion=_SUGGESTIONS[issue_type],
        )

    def _check_node(
        self,
        node: tree_sitter.Node,
        issues: list[BuiltinShadowIssue],
    ) -> int:
        ntype = node.type

        if ntype == "assignment":
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                name = _txt(left)
                if name in PYTHON_BUILTINS:
                    issues.append(
                        self._make_issue(
                            ISSUE_SHADOWED_ASSIGNMENT, name,
                            node.start_point[0] + 1,
                        )
                    )
            return 1

        if ntype == "function_definition":
            name = _get_name(node)
            if name and name in PYTHON_BUILTINS:
                issues.append(
                    self._make_issue(
                        ISSUE_SHADOWED_FUNCTION, name,
                        node.start_point[0] + 1,
                    )
                )
            for child in node.children:
                if child.type == "parameters":
                    self._check_params(child, issues)
            return 1

        if ntype == "class_definition":
            name = _get_name(node)
            if name and name in PYTHON_BUILTINS:
                issues.append(
                    self._make_issue(
                        ISSUE_SHADOWED_CLASS, name,
                        node.start_point[0] + 1,
                    )
                )
            return 1

        if ntype == "for_statement":
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    if name in PYTHON_BUILTINS:
                        issues.append(
                            self._make_issue(
                                ISSUE_SHADOWED_FOR_TARGET, name,
                                child.start_point[0] + 1,
                            )
                        )
            return 1

        if ntype in {"import_from_statement", "import_statement"}:
            self._check_import(node, issues)
            return 1

        return 0

    def _check_params(
        self,
        params_node: tree_sitter.Node,
        issues: list[BuiltinShadowIssue],
    ) -> None:
        for child in params_node.children:
            if child.type == "identifier":
                name = _txt(child)
                if name in PYTHON_BUILTINS:
                    issues.append(
                        self._make_issue(
                            ISSUE_SHADOWED_PARAMETER, name,
                            child.start_point[0] + 1,
                        )
                    )
            elif child.type == "typed_parameter":
                for tc in child.children:
                    if tc.type == "identifier":
                        name = _txt(tc)
                        if name in PYTHON_BUILTINS:
                            issues.append(
                                self._make_issue(
                                    ISSUE_SHADOWED_PARAMETER, name,
                                    tc.start_point[0] + 1,
                                )
                            )
            elif child.type == "default_parameter":
                for tc in child.children:
                    if tc.type == "identifier":
                        name = _txt(tc)
                        if name in PYTHON_BUILTINS:
                            issues.append(
                                self._make_issue(
                                    ISSUE_SHADOWED_PARAMETER, name,
                                    tc.start_point[0] + 1,
                                )
                            )
                        break
            elif child.type == "typed_default_parameter":
                for tc in child.children:
                    if tc.type == "identifier":
                        name = _txt(tc)
                        if name in PYTHON_BUILTINS:
                            issues.append(
                                self._make_issue(
                                    ISSUE_SHADOWED_PARAMETER, name,
                                    tc.start_point[0] + 1,
                                )
                            )
                        break

    def _check_import(
        self,
        node: tree_sitter.Node,
        issues: list[BuiltinShadowIssue],
    ) -> None:
        if node.type == "import_from_statement":
            saw_import_keyword = False
            for child in node.children:
                if child.type == "from":
                    continue
                if child.type == "import":
                    saw_import_keyword = True
                    continue
                if not saw_import_keyword:
                    continue
                if child.type == "wildcard_import":
                    continue
                if child.type == "aliased_import":
                    for ac in child.children:
                        if ac.type == "identifier":
                            name = _txt(ac)
                            if name in PYTHON_BUILTINS:
                                issues.append(
                                    self._make_issue(
                                        ISSUE_SHADOWED_IMPORT, name,
                                        ac.start_point[0] + 1,
                                    )
                                )
                            break
                    continue
                resolved = _check_dotted_name(child)
                if resolved is None:
                    if child.type == "identifier":
                        resolved = _txt(child)
                    else:
                        continue
                if resolved in PYTHON_BUILTINS:
                    issues.append(
                        self._make_issue(
                            ISSUE_SHADOWED_IMPORT, resolved,
                            child.start_point[0] + 1,
                        )
                    )
