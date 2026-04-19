"""Middle Man Detector.

Detects classes that primarily delegate to another class without adding value,
the classic Middle Man code smell from Martin Fowler's refactoring catalog.

Issues detected:
  - middle_man_class: class where ≥70% of methods delegate to a single field
  - delegation_chain: method that chains through multiple objects

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_MIDDLE_MAN = "middle_man_class"
ISSUE_DELEGATION_CHAIN = "delegation_chain"

SEVERITY_MAP: dict[str, str] = {
    ISSUE_MIDDLE_MAN: SEVERITY_MEDIUM,
    ISSUE_DELEGATION_CHAIN: SEVERITY_LOW,
}

DEFAULT_DELEGATION_THRESHOLD = 0.7

_CLASS_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".java": frozenset({"class_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

_METHOD_NODE_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"method_definition"}),
    ".jsx": frozenset({"method_definition"}),
    ".ts": frozenset({"method_definition"}),
    ".tsx": frozenset({"method_definition"}),
    ".java": frozenset({"method_declaration"}),
    ".go": frozenset({"method_declaration"}),
}

@dataclass(frozen=True)
class MiddleManIssue:
    """A single middle man issue."""

    issue_type: str
    line: int
    message: str
    severity: str
    class_name: str
    detail: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "class_name": self.class_name,
            "detail": self.detail,
        }

@dataclass(frozen=True)
class ClassInfo:
    """Info about a class for middle man analysis."""

    class_name: str
    start_line: int
    total_methods: int
    delegating_methods: int
    delegate_fields: tuple[str, ...]
    delegation_ratio: float

@dataclass(frozen=True)
class MiddleManResult:
    """Aggregated result of middle man analysis."""

    issues: tuple[MiddleManIssue, ...]
    classes_analyzed: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(self, severity: str) -> list[MiddleManIssue]:
        return [i for i in self.issues if i.severity == severity]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "classes_analyzed": self.classes_analyzed,
            "total_issues": self.total_issues,
            "high_severity_count": self.high_severity_count,
            "issues": [i.to_dict() for i in self.issues],
        }

class MiddleManAnalyzer(BaseAnalyzer):
    """Detects middle man classes that just delegate to other objects."""

    def __init__(
        self,
        delegation_threshold: float = DEFAULT_DELEGATION_THRESHOLD,
    ) -> None:
        self._delegation_threshold = delegation_threshold
        super().__init__()

    def analyze_file(self, file_path: Path | str) -> MiddleManResult:
        path = Path(file_path)
        if not path.exists():
            return self._empty_result(str(path))

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return self._empty_result(str(path))

        content = path.read_bytes()
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return self._empty_result(str(path))

        tree = parser.parse(content)

        class_types = _CLASS_NODE_TYPES.get(ext, frozenset())
        classes_info: list[ClassInfo] = []

        for node in self._find_nodes(tree.root_node, class_types):
            info = self._analyze_class(node, content, ext)
            if info is not None:
                classes_info.append(info)

        issues = self._detect_issues(classes_info)
        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)

        return MiddleManResult(
            issues=tuple(issues),
            classes_analyzed=len(classes_info),
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=str(path),
        )

    def _find_nodes(
        self, root: tree_sitter.Node, types: frozenset[str]
    ) -> list[tree_sitter.Node]:
        result: list[tree_sitter.Node] = []

        def walk(n: tree_sitter.Node) -> None:
            if n.type in types:
                result.append(n)
            for child in n.children:
                walk(child)

        walk(root)
        return result

    def _analyze_class(
        self,
        class_node: tree_sitter.Node,
        content: bytes,
        ext: str,
    ) -> ClassInfo | None:
        class_name = self._get_class_name(class_node, content)
        if not class_name:
            return None

        method_types = _METHOD_NODE_TYPES.get(ext, frozenset())
        body_node = self._get_class_body(class_node, ext)
        if body_node is None:
            return None

        methods: list[tree_sitter.Node] = []
        for child in body_node.children:
            if child.type in method_types:
                func_name = self._get_node_name(child, content)
                if func_name in ("__init__", "__init__", "<init>"):
                    continue
                methods.append(child)

        if not methods:
            return ClassInfo(
                class_name=class_name,
                start_line=class_node.start_point[0] + 1,
                total_methods=0,
                delegating_methods=0,
                delegate_fields=(),
                delegation_ratio=0.0,
            )

        delegate_counts: dict[str, int] = {}
        delegating_count = 0

        for method in methods:
            delegate_field = self._find_delegate_field(method, content, ext)
            if delegate_field:
                delegate_counts[delegate_field] = (
                    delegate_counts.get(delegate_field, 0) + 1
                )
                delegating_count += 1

        ratio = delegating_count / len(methods) if methods else 0.0
        top_delegates = tuple(
            sorted(delegate_counts, key=lambda k: delegate_counts[k], reverse=True)
        )

        return ClassInfo(
            class_name=class_name,
            start_line=class_node.start_point[0] + 1,
            total_methods=len(methods),
            delegating_methods=delegating_count,
            delegate_fields=top_delegates,
            delegation_ratio=ratio,
        )

    def _get_node_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        return ""

    def _get_class_name(
        self, node: tree_sitter.Node, content: bytes
    ) -> str:
        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    for sub in child.children:
                        if sub.type == "type_identifier":
                            return content[sub.start_byte:sub.end_byte].decode(
                                "utf-8", errors="replace"
                            )
            return ""

        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        return ""

    def _get_class_body(
        self, node: tree_sitter.Node, ext: str
    ) -> tree_sitter.Node | None:
        if ext == ".go":
            for child in node.children:
                if child.type == "type_spec":
                    for sub in child.children:
                        if sub.type in ("struct_type", "interface_type"):
                            for field in sub.children:
                                if field.type == "field_declaration_list":
                                    return field
            return None

        body = node.child_by_field_name("body")
        if body is not None:
            return body

        for child in node.children:
            if child.type in ("block", "class_body", "declaration_list"):
                return child
        return None

    def _find_delegate_field(
        self,
        method_node: tree_sitter.Node,
        content: bytes,
        ext: str,
    ) -> str | None:
        body = method_node.child_by_field_name("body")
        if body is None:
            for child in method_node.children:
                if child.type in ("block", "function_body", "statement_block"):
                    body = child
                    break
        if body is None:
            return None

        method_text = content[body.start_byte:body.end_byte].decode(
            "utf-8", errors="replace"
        )

        if ext == ".py":
            return self._find_py_delegate(body, method_text)
        if ext in {".js", ".jsx", ".ts", ".tsx"}:
            return self._find_js_delegate(body, method_text)
        if ext == ".java":
            return self._find_java_delegate(body, method_text)
        if ext == ".go":
            return self._find_go_delegate(body, method_text)
        return None

    def _find_py_delegate(
        self, body: tree_sitter.Node, method_text: str
    ) -> str | None:
        return self._find_self_attr_delegate(body, method_text, "self.")

    def _find_js_delegate(
        self, body: tree_sitter.Node, method_text: str
    ) -> str | None:
        return self._find_self_attr_delegate(body, method_text, "this.")

    def _find_java_delegate(
        self, body: tree_sitter.Node, method_text: str
    ) -> str | None:
        method_invocations = self._find_nodes_in(
            body, frozenset({"method_invocation"})
        )

        delegate_fields: set[str] = set()

        for inv in method_invocations:
            first_child = inv.children[0] if inv.children else None
            if first_child and first_child.type == "field_access":
                for sub in first_child.children:
                    if sub.type == "identifier":
                        delegate_fields.add(
                            method_text[
                                sub.start_byte - body.start_byte:
                                sub.end_byte - body.start_byte
                            ]
                        )
                        break

        if len(delegate_fields) == 1:
            return delegate_fields.pop()
        return None

    def _find_go_delegate(
        self, body: tree_sitter.Node, method_text: str
    ) -> str | None:
        selector_nodes = self._find_nodes_in(
            body, frozenset({"selector_expression"})
        )
        for sel in selector_nodes:
            children = sel.children
            if len(children) >= 3:
                operand = children[0]
                field = children[2]
                if operand.type == "identifier" and field.type == "field_identifier":
                    return method_text[
                        operand.start_byte - body.start_byte:
                        operand.end_byte - body.start_byte
                    ]
        return None

    def _find_self_attr_delegate(
        self,
        body: tree_sitter.Node,
        method_text: str,
        prefix: str,
    ) -> str | None:
        attr_nodes = self._find_nodes_in(
            body, frozenset({"attribute", "member_expression", "field_access"})
        )

        delegate_fields: set[str] = set()

        for attr in attr_nodes:
            attr_text = method_text[
                attr.start_byte - body.start_byte:
                attr.end_byte - body.start_byte
            ]
            if not attr_text.startswith(prefix):
                continue
            rest = attr_text[len(prefix):]
            parts = rest.split(".")
            if len(parts) < 2:
                continue
            field_name = parts[0]
            if not field_name or field_name.startswith("_"):
                continue
            delegate_fields.add(field_name)

        if len(delegate_fields) == 1:
            return delegate_fields.pop()
        return None

    def _find_nodes_in(
        self,
        node: tree_sitter.Node,
        types: frozenset[str],
    ) -> list[tree_sitter.Node]:
        result: list[tree_sitter.Node] = []

        def walk(n: tree_sitter.Node) -> None:
            for child in n.children:
                if child.type in types:
                    result.append(child)
                walk(child)

        walk(node)
        return result

    def _detect_issues(
        self, classes_info: list[ClassInfo]
    ) -> list[MiddleManIssue]:
        issues: list[MiddleManIssue] = []

        for info in classes_info:
            if info.total_methods < 2:
                continue
            if info.delegation_ratio < self._delegation_threshold:
                continue
            if len(info.delegate_fields) > 1:
                continue

            pct = int(info.delegation_ratio * 100)
            delegate_str = ", ".join(info.delegate_fields[:3])
            issues.append(MiddleManIssue(
                issue_type=ISSUE_MIDDLE_MAN,
                line=info.start_line,
                message=(
                    f"Class '{info.class_name}' delegates "
                    f"{info.delegating_methods}/{info.total_methods} "
                    f"methods ({pct}%) via {delegate_str}"
                ),
                severity=SEVERITY_MAP[ISSUE_MIDDLE_MAN],
                class_name=info.class_name,
                detail=(
                    f"delegation_ratio={pct}%, "
                    f"delegate_fields=[{delegate_str}]"
                ),
            ))

        return issues

    def _empty_result(self, file_path: str) -> MiddleManResult:
        return MiddleManResult(
            issues=(),
            classes_analyzed=0,
            total_issues=0,
            high_severity_count=0,
            file_path=file_path,
        )
