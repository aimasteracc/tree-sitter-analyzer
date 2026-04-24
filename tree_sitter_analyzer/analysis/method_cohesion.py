"""Method Cohesion Analyzer (LCOM4).

Detects classes with low method cohesion using the LCOM4 metric
(Lack of Cohesion of Methods, version 4).

LCOM4 counts the number of connected components in a graph where:
  - Nodes = methods (including __init__/constructor)
  - Edges = two methods share at least one instance field access

LCOM4 = 1 means the class is cohesive (all methods access overlapping fields).
LCOM4 > 1 means the class contains disjoint method groups that should be split.

Issue types:
  - low_cohesion: LCOM4 > 1, class should be split into focused classes (medium)

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

SEVERITY_MEDIUM = "medium"

ISSUE_LOW_COHESION = "low_cohesion"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_LOW_COHESION: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_LOW_COHESION: "Class has low method cohesion (LCOM4 > 1): methods operate on disjoint field sets",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_LOW_COHESION: "Split the class into separate classes, one per connected component of methods",
}


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class CohesionIssue:
    line: int
    issue_type: str
    severity: str
    class_name: str
    lcom4: int
    method_count: int
    field_count: int
    component_count: int
    description: str
    suggestion: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "class_name": self.class_name,
            "lcom4": self.lcom4,
            "method_count": self.method_count,
            "field_count": self.field_count,
            "component_count": self.component_count,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class CohesionResult:
    issues: tuple[CohesionIssue, ...]
    total_classes: int
    cohesive_classes: int
    file_path: str
    language: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "language": self.language,
            "total_classes": self.total_classes,
            "cohesive_classes": self.cohesive_classes,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


def _empty_result(file_path: str, language: str) -> CohesionResult:
    return CohesionResult(
        issues=(),
        total_classes=0,
        cohesive_classes=0,
        file_path=file_path,
        language=language,
    )


def _compute_connected_components(
    method_fields: dict[str, frozenset[str]],
) -> list[frozenset[str]]:
    """Compute connected components via BFS on shared-field graph."""
    if not method_fields:
        return []

    adj: dict[str, set[str]] = {m: set() for m in method_fields}
    methods = list(method_fields.keys())
    for i in range(len(methods)):
        for j in range(i + 1, len(methods)):
            mi, mj = methods[i], methods[j]
            if method_fields[mi] & method_fields[mj]:
                adj[mi].add(mj)
                adj[mj].add(mi)

    visited: set[str] = set()
    components: list[frozenset[str]] = []
    for m in methods:
        if m in visited:
            continue
        component: set[str] = set()
        queue = [m]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(frozenset(component))

    return components


class MethodCohesionAnalyzer(BaseAnalyzer):
    """Detects classes with low method cohesion (LCOM4 > 1)."""

    def analyze_file(self, file_path: Path | str) -> CohesionResult:
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
            issues, total = self._analyze_python(content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            issues, total = self._analyze_javascript(content)
        elif ext == ".java":
            issues, total = self._analyze_java(content)
        elif ext == ".go":
            issues, total = self._analyze_go(content)
        else:
            issues, total = [], 0

        issue_tuple = tuple(issues)
        cohesive = total - len(issue_tuple)
        return CohesionResult(
            issues=issue_tuple,
            total_classes=total,
            cohesive_classes=cohesive,
            file_path=str(path),
            language=lang,
        )

    def _analyze_python(
        self, content: bytes,
    ) -> tuple[list[CohesionIssue], int]:
        language, parser = self._get_parser(".py")
        if language is None or parser is None:
            return [], 0

        tree = parser.parse(content)
        issues: list[CohesionIssue] = []
        classes = self._collect_py_classes(tree.root_node)
        total = len(classes)

        for cls_node, cls_name in classes:
            method_fields = self._py_method_field_map(cls_node)
            if len(method_fields) < 2:
                continue
            components = _compute_connected_components(method_fields)
            lcom4 = len(components)
            if lcom4 > 1:
                all_fields: set[str] = set()
                for fs in method_fields.values():
                    all_fields.update(fs)
                issues.append(CohesionIssue(
                    line=cls_node.start_point[0] + 1,
                    issue_type=ISSUE_LOW_COHESION,
                    severity=_SEVERITY_MAP[ISSUE_LOW_COHESION],
                    class_name=cls_name,
                    lcom4=lcom4,
                    method_count=len(method_fields),
                    field_count=len(all_fields),
                    component_count=lcom4,
                    description=(
                        f"Class '{cls_name}' has LCOM4={lcom4}: "
                        f"{len(method_fields)} methods form {lcom4} disjoint groups"
                    ),
                    suggestion=_SUGGESTIONS[ISSUE_LOW_COHESION],
                ))

        return issues, total

    def _collect_py_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        if node.type == "class_definition":
            name = ""
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    break
            if name:
                results.append((node, name))

        for child in node.children:
            results.extend(self._collect_py_classes(child))

        return results

    def _py_method_field_map(
        self, cls_node: tree_sitter.Node,
    ) -> dict[str, frozenset[str]]:
        method_fields: dict[str, frozenset[str]] = {}
        for child in cls_node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        name_node = stmt.child_by_field_name("name")
                        name = _txt(name_node) if name_node else ""
                        if not name or name == "__init__":
                            continue
                        fields = self._py_collect_self_fields(stmt)
                        if fields:
                            method_fields[name] = frozenset(fields)

        return method_fields

    def _py_collect_self_fields(
        self, func_node: tree_sitter.Node,
    ) -> set[str]:
        fields: set[str] = set()
        self._walk_py_self_access(func_node, fields)
        return fields

    def _walk_py_self_access(
        self, node: tree_sitter.Node, fields: set[str],
    ) -> None:
        if node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            if obj and attr and _txt(obj) == "self":
                fields.add(_txt(attr))

        for child in node.children:
            self._walk_py_self_access(child, fields)

    # -- JavaScript/TypeScript --------------------------------------------

    def _analyze_javascript(
        self, content: bytes,
    ) -> tuple[list[CohesionIssue], int]:
        language, parser = self._get_parser(".js")
        if language is None or parser is None:
            return [], 0

        tree = parser.parse(content)
        issues: list[CohesionIssue] = []
        classes = self._collect_js_classes(tree.root_node)
        total = len(classes)

        for cls_node, cls_name in classes:
            method_fields = self._js_method_field_map(cls_node)
            if len(method_fields) < 2:
                continue
            components = _compute_connected_components(method_fields)
            lcom4 = len(components)
            if lcom4 > 1:
                all_fields: set[str] = set()
                for fs in method_fields.values():
                    all_fields.update(fs)
                issues.append(CohesionIssue(
                    line=cls_node.start_point[0] + 1,
                    issue_type=ISSUE_LOW_COHESION,
                    severity=_SEVERITY_MAP[ISSUE_LOW_COHESION],
                    class_name=cls_name,
                    lcom4=lcom4,
                    method_count=len(method_fields),
                    field_count=len(all_fields),
                    component_count=lcom4,
                    description=(
                        f"Class '{cls_name}' has LCOM4={lcom4}: "
                        f"{len(method_fields)} methods form {lcom4} disjoint groups"
                    ),
                    suggestion=_SUGGESTIONS[ISSUE_LOW_COHESION],
                ))

        return issues, total

    def _collect_js_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        if node.type == "class_declaration":
            name = ""
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    break
            if name:
                results.append((node, name))

        for child in node.children:
            results.extend(self._collect_js_classes(child))

        return results

    def _js_method_field_map(
        self, cls_node: tree_sitter.Node,
    ) -> dict[str, frozenset[str]]:
        method_fields: dict[str, frozenset[str]] = {}
        for child in cls_node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        name_node = member.child_by_field_name("name")
                        name = _txt(name_node) if name_node else ""
                        if not name or name == "constructor":
                            continue
                        fields = self._js_collect_this_fields(member)
                        if fields:
                            method_fields[name] = frozenset(fields)

        return method_fields

    def _js_collect_this_fields(
        self, method_node: tree_sitter.Node,
    ) -> set[str]:
        fields: set[str] = set()
        self._walk_js_this_access(method_node, fields)
        return fields

    def _walk_js_this_access(
        self, node: tree_sitter.Node, fields: set[str],
    ) -> None:
        if node.type == "member_expression":
            obj = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            if obj and prop and _txt(obj) == "this":
                fields.add(_txt(prop))

        for child in node.children:
            self._walk_js_this_access(child, fields)

    # -- Java -------------------------------------------------------------

    def _analyze_java(
        self, content: bytes,
    ) -> tuple[list[CohesionIssue], int]:
        language, parser = self._get_parser(".java")
        if language is None or parser is None:
            return [], 0

        tree = parser.parse(content)
        issues: list[CohesionIssue] = []
        classes = self._collect_java_classes(tree.root_node)
        total = len(classes)

        for cls_node, cls_name in classes:
            method_fields = self._java_method_field_map(cls_node, cls_name)
            if len(method_fields) < 2:
                continue
            components = _compute_connected_components(method_fields)
            lcom4 = len(components)
            if lcom4 > 1:
                all_fields: set[str] = set()
                for fs in method_fields.values():
                    all_fields.update(fs)
                issues.append(CohesionIssue(
                    line=cls_node.start_point[0] + 1,
                    issue_type=ISSUE_LOW_COHESION,
                    severity=_SEVERITY_MAP[ISSUE_LOW_COHESION],
                    class_name=cls_name,
                    lcom4=lcom4,
                    method_count=len(method_fields),
                    field_count=len(all_fields),
                    component_count=lcom4,
                    description=(
                        f"Class '{cls_name}' has LCOM4={lcom4}: "
                        f"{len(method_fields)} methods form {lcom4} disjoint groups"
                    ),
                    suggestion=_SUGGESTIONS[ISSUE_LOW_COHESION],
                ))

        return issues, total

    def _collect_java_classes(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        results: list[tuple[tree_sitter.Node, str]] = []
        if node.type in ("class_declaration", "record_declaration"):
            name = ""
            for child in node.children:
                if child.type == "identifier":
                    name = _txt(child)
                    break
            if name:
                results.append((node, name))

        for child in node.children:
            results.extend(self._collect_java_classes(child))

        return results

    def _java_method_field_map(
        self, cls_node: tree_sitter.Node, cls_name: str,
    ) -> dict[str, frozenset[str]]:
        method_fields: dict[str, frozenset[str]] = {}
        body_node = None
        for child in cls_node.children:
            if child.type == "class_body":
                body_node = child
                break
        if body_node is None:
            return method_fields

        for member in body_node.children:
            if member.type == "method_declaration":
                name_node = member.child_by_field_name("name")
                name = _txt(name_node) if name_node else ""
                if not name or name == cls_name:
                    continue
                fields = self._java_collect_this_fields(member)
                if fields:
                    method_fields[name] = frozenset(fields)

        return method_fields

    def _java_collect_this_fields(
        self, method_node: tree_sitter.Node,
    ) -> set[str]:
        fields: set[str] = set()
        self._walk_java_this_access(method_node, fields)
        return fields

    def _walk_java_this_access(
        self, node: tree_sitter.Node, fields: set[str],
    ) -> None:
        if node.type == "field_access":
            obj = node.child_by_field_name("object")
            field_node = node.child_by_field_name("field")
            if obj and field_node and _txt(obj) == "this":
                fields.add(_txt(field_node))

        for child in node.children:
            self._walk_java_this_access(child, fields)

    # -- Go ---------------------------------------------------------------

    def _analyze_go(
        self, content: bytes,
    ) -> tuple[list[CohesionIssue], int]:
        language, parser = self._get_parser(".go")
        if language is None or parser is None:
            return [], 0

        tree = parser.parse(content)

        # Group methods by receiver type
        type_methods: dict[str, list[tuple[tree_sitter.Node, str, str]]] = {}
        methods = self._collect_go_methods(tree.root_node)
        for func_node, func_name, recv_name, recv_type in methods:
            if recv_type not in type_methods:
                type_methods[recv_type] = []
            type_methods[recv_type].append(
                (func_node, func_name, recv_name),
            )

        issues: list[CohesionIssue] = []
        total = len(type_methods)

        for type_name, method_list in type_methods.items():
            if len(method_list) < 2:
                continue
            method_fields: dict[str, frozenset[str]] = {}
            for func_node, func_name, recv_name in method_list:
                fields = self._go_collect_receiver_fields(
                    func_node, recv_name,
                )
                if fields:
                    method_fields[func_name] = frozenset(fields)

            if len(method_fields) < 2:
                continue

            components = _compute_connected_components(method_fields)
            lcom4 = len(components)
            if lcom4 > 1:
                all_fields: set[str] = set()
                for fs in method_fields.values():
                    all_fields.update(fs)
                issues.append(CohesionIssue(
                    line=method_list[0][0].start_point[0] + 1,
                    issue_type=ISSUE_LOW_COHESION,
                    severity=_SEVERITY_MAP[ISSUE_LOW_COHESION],
                    class_name=type_name,
                    lcom4=lcom4,
                    method_count=len(method_fields),
                    field_count=len(all_fields),
                    component_count=lcom4,
                    description=(
                        f"Type '{type_name}' has LCOM4={lcom4}: "
                        f"{len(method_fields)} methods form {lcom4} disjoint groups"
                    ),
                    suggestion=_SUGGESTIONS[ISSUE_LOW_COHESION],
                ))

        return issues, total

    def _collect_go_methods(
        self, node: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str, str, str]]:
        results: list[tuple[tree_sitter.Node, str, str, str]] = []

        if node.type == "method_declaration":
            name = ""
            recv_name = ""
            recv_type = ""
            found_receiver = False
            for child in node.children:
                if child.type == "field_identifier" and not name:
                    name = _txt(child)
                elif child.type == "parameter_list" and not found_receiver:
                    found_receiver = True
                    for param in child.children:
                        if param.type == "parameter_declaration":
                            for sc in param.children:
                                if sc.type == "identifier":
                                    recv_name = _txt(sc)
                                elif sc.type in (
                                    "type_identifier",
                                    "pointer_type",
                                    "generic_type",
                                ):
                                    recv_type = _txt(sc).lstrip("*")
                            break
            if name and recv_name:
                results.append((node, name, recv_name, recv_type))

        if node.type != "method_declaration":
            for child in node.children:
                results.extend(self._collect_go_methods(child))

        return results

    def _go_collect_receiver_fields(
        self, func_node: tree_sitter.Node, recv_name: str,
    ) -> set[str]:
        fields: set[str] = set()
        self._walk_go_receiver_access(func_node, recv_name, fields)
        return fields

    def _walk_go_receiver_access(
        self,
        node: tree_sitter.Node,
        recv_name: str,
        fields: set[str],
    ) -> None:
        if node.type == "selector_expression":
            operand = node.child_by_field_name("operand")
            field_node = node.child_by_field_name("field")
            if operand and field_node and _txt(operand) == recv_name:
                fields.add(_txt(field_node))

        for child in node.children:
            self._walk_go_receiver_access(child, recv_name, fields)
