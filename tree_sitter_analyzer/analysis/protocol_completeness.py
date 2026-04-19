"""Protocol Completeness Analyzer.

Detects classes that partially implement a known protocol, missing required
counterpart methods:

  - Python: __eq__ without __hash__, __enter__ without __exit__,
    __iter__ without __next__, __get__ without __set__/__delete__
  - Java: equals() without hashCode(), compareTo() without equals()

Incomplete protocol implementations cause silent runtime bugs: objects
become unhashable, context managers fail to clean up, descriptors break.

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

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

ISSUE_MISSING_HASH = "missing_hash"
ISSUE_MISSING_EXIT = "missing_exit"
ISSUE_MISSING_NEXT = "missing_next"
ISSUE_MISSING_SET_OR_DELETE = "missing_set_or_delete"
ISSUE_MISSING_HASHCODE = "missing_hashcode"
ISSUE_MISSING_EQUALS = "missing_equals_for_compareto"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_MISSING_HASH: SEVERITY_HIGH,
    ISSUE_MISSING_EXIT: SEVERITY_HIGH,
    ISSUE_MISSING_NEXT: SEVERITY_MEDIUM,
    ISSUE_MISSING_SET_OR_DELETE: SEVERITY_MEDIUM,
    ISSUE_MISSING_HASHCODE: SEVERITY_HIGH,
    ISSUE_MISSING_EQUALS: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_MISSING_HASH: (
        "Class defines __eq__ without __hash__: instances become unhashable, "
        "breaking dict/set usage"
    ),
    ISSUE_MISSING_EXIT: (
        "Class defines __enter__ without __exit__: context manager protocol "
        "is incomplete"
    ),
    ISSUE_MISSING_NEXT: (
        "Class defines __iter__ without __next__: iterator protocol is incomplete"
    ),
    ISSUE_MISSING_SET_OR_DELETE: (
        "Class defines __get__ without __set__ or __delete__: descriptor "
        "protocol is incomplete"
    ),
    ISSUE_MISSING_HASHCODE: (
        "Class defines equals() without hashCode(): HashMap/HashSet behavior "
        "becomes inconsistent"
    ),
    ISSUE_MISSING_EQUALS: (
        "Class defines compareTo() without equals(): ordering contract is "
        "inconsistent (compareTo should be consistent with equals)"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_MISSING_HASH: "Add __hash__ to maintain hashability, or explicitly set __hash__ = None.",
    ISSUE_MISSING_EXIT: "Add __exit__ to complete the context manager protocol.",
    ISSUE_MISSING_NEXT: "Add __next__ to make the class a proper iterator.",
    ISSUE_MISSING_SET_OR_DELETE: "Add __set__ or __delete__ to complete the descriptor protocol.",
    ISSUE_MISSING_HASHCODE: "Override hashCode() whenever you override equals().",
    ISSUE_MISSING_EQUALS: "Override equals() to be consistent with compareTo().",
}

# Python protocol pairs: (trigger_method, required_methods)
_PYTHON_PROTOCOLS: list[tuple[str, list[str], str]] = [
    ("__eq__", ["__hash__"], ISSUE_MISSING_HASH),
    ("__enter__", ["__exit__"], ISSUE_MISSING_EXIT),
    ("__iter__", ["__next__"], ISSUE_MISSING_NEXT),
    ("__get__", ["__set__", "__delete__"], ISSUE_MISSING_SET_OR_DELETE),
]

# Java protocol pairs
_JAVA_PROTOCOLS: list[tuple[str, list[str], str]] = [
    ("equals", ["hashCode"], ISSUE_MISSING_HASHCODE),
    ("compareTo", ["equals"], ISSUE_MISSING_EQUALS),
]

_CLASS_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".java": frozenset({"class_declaration", "interface_declaration", "enum_declaration"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

_BODY_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"block"}),
    ".java": frozenset({"class_body", "interface_body", "enum_body"}),
    ".js": frozenset({"class_body"}),
    ".jsx": frozenset({"class_body"}),
    ".ts": frozenset({"class_body"}),
    ".tsx": frozenset({"class_body"}),
    ".go": frozenset({}),
}

_METHOD_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".java": frozenset({"method_declaration"}),
    ".js": frozenset({"method_definition", "public_field_definition"}),
    ".jsx": frozenset({"method_definition", "public_field_definition"}),
    ".ts": frozenset({"method_definition", "public_field_definition"}),
    ".tsx": frozenset({"method_definition", "public_field_definition"}),
    ".go": frozenset({"method_declaration", "function_declaration"}),
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _get_class_name(node: tree_sitter.Node, ext: str) -> str:
    if ext == ".py":
        for child in node.children:
            if child.is_named:
                return _txt(child)
    elif ext == ".java":
        for child in node.children_by_field_name("name"):
            return _txt(child)
        for child in node.children:
            if child.is_named and child.type == "identifier":
                return _txt(child)
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        for child in node.children:
            if child.is_named and child.type == "identifier":
                return _txt(child)
    elif ext == ".go":
        for child in node.children:
            if child.type == "type_spec":
                for tc in child.children:
                    if tc.type == "type_identifier":
                        return _txt(tc)
    return "<anonymous>"


def _get_method_name(node: tree_sitter.Node, ext: str) -> str:
    if ext == ".py":
        for child in node.children:
            if child.is_named:
                return _txt(child)
    elif ext == ".java":
        for child in node.children_by_field_name("name"):
            return _txt(child)
        for child in node.children:
            if child.is_named and child.type == "identifier":
                return _txt(child)
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        for child in node.children:
            if child.is_named and child.type == "property_identifier":
                return _txt(child)
    elif ext == ".go":
        for child in node.children_by_field_name("name"):
            return _txt(child)
    return ""


def _collect_method_names(
    class_node: tree_sitter.Node, ext: str,
) -> set[str]:
    method_types = _METHOD_NODE_TYPES.get(ext, frozenset())
    body_types = _BODY_NODE_TYPES.get(ext, frozenset())
    class_types = _CLASS_NODE_TYPES.get(ext, frozenset())
    names: set[str] = set()

    if ext == ".go":
        for child in class_node.children:
            if child.type in method_types:
                name = _get_method_name(child, ext)
                if name:
                    names.add(name)
        return names

    search_nodes: list[tree_sitter.Node] = []
    for child in class_node.children:
        if not body_types or child.type in body_types:
            search_nodes.append(child)

    for body in search_nodes:
        for child in body.children:
            if child.type in method_types:
                name = _get_method_name(child, ext)
                if name:
                    names.add(name)
            elif child.type not in class_types and body_types:
                for grandchild in child.children:
                    if grandchild.type in method_types:
                        name = _get_method_name(grandchild, ext)
                        if name:
                            names.add(name)
    return names


def _check_protocols(
    class_name: str,
    method_names: set[str],
    protocols: list[tuple[str, list[str], str]],
    issues: list[ProtocolCompletenessIssue],
    line: int,
) -> None:
    for trigger, required, issue_type in protocols:
        if trigger not in method_names:
            continue
        if issue_type == ISSUE_MISSING_SET_OR_DELETE:
            if not any(r in method_names for r in required):
                issues.append(ProtocolCompletenessIssue(
                    line=line,
                    issue_type=issue_type,
                    severity=_SEVERITY_MAP[issue_type],
                    class_name=class_name,
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    missing_methods=required,
                    trigger_method=trigger,
                ))
        else:
            missing = [r for r in required if r not in method_names]
            if missing:
                issues.append(ProtocolCompletenessIssue(
                    line=line,
                    issue_type=issue_type,
                    severity=_SEVERITY_MAP[issue_type],
                    class_name=class_name,
                    description=_DESCRIPTIONS[issue_type],
                    suggestion=_SUGGESTIONS[issue_type],
                    missing_methods=missing,
                    trigger_method=trigger,
                ))


@dataclass(frozen=True)
class ProtocolCompletenessIssue:
    line: int
    issue_type: str
    severity: str
    class_name: str
    description: str
    suggestion: str
    missing_methods: list[str]
    trigger_method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "class_name": self.class_name,
            "description": self.description,
            "suggestion": self.suggestion,
            "missing_methods": self.missing_methods,
            "trigger_method": self.trigger_method,
        }


@dataclass
class ProtocolCompletenessResult:
    file_path: str
    classes_checked: int
    issues: list[ProtocolCompletenessIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "classes_checked": self.classes_checked,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class ProtocolCompletenessAnalyzer(BaseAnalyzer):
    """Detects incomplete protocol implementations in class definitions."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
        }

    def analyze_file(
        self, file_path: str | Path,
    ) -> ProtocolCompletenessResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return ProtocolCompletenessResult(
                file_path=str(path),
                classes_checked=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return ProtocolCompletenessResult(
                file_path=str(path),
                classes_checked=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)
        issues: list[ProtocolCompletenessIssue] = []
        classes_checked = 0

        class_types = _CLASS_NODE_TYPES.get(ext, frozenset())
        protocols = self._get_protocols(ext)

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in class_types:
                classes_checked += 1
                class_name = _get_class_name(node, ext)
                method_names = _collect_method_names(node, ext)
                _check_protocols(
                    class_name, method_names, protocols,
                    issues, node.start_point[0] + 1,
                )
            for child in node.children:
                stack.append(child)

        return ProtocolCompletenessResult(
            file_path=str(path),
            classes_checked=classes_checked,
            issues=issues,
        )

    def _get_protocols(
        self, ext: str,
    ) -> list[tuple[str, list[str], str]]:
        if ext == ".py":
            return _PYTHON_PROTOCOLS
        if ext == ".java":
            return _JAVA_PROTOCOLS
        return []
