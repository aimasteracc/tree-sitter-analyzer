"""Temporal Coupling Detector.

Detects hidden method ordering dependencies within classes: when one method
reads an instance variable that is only written by another method, the reader
must be called after the writer — a temporal coupling that is invisible in
the type system.

Issue types:
  - temporal_coupling: method reads self.X but only method Y writes it (medium)

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

SEVERITY_MEDIUM = "medium"

ISSUE_TEMPORAL_COUPLING = "temporal_coupling"

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_TEMPORAL_COUPLING: SEVERITY_MEDIUM,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_TEMPORAL_COUPLING: (
        "Method reads instance variable written only by another method — "
        "hidden ordering dependency"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_TEMPORAL_COUPLING: (
        "Initialize the variable in __init__/constructor, or restructure "
        "to make the ordering explicit."
    ),
}

_PY_INIT_NAMES: frozenset[str] = frozenset({
    "__init__", "__new__", "__init_subclass__", "__post_init__",
})

_PY_CLASS_TYPES: frozenset[str] = frozenset({"class_definition"})
_JS_CLASS_TYPES: frozenset[str] = frozenset({"class_declaration"})
_JAVA_CLASS_TYPES: frozenset[str] = frozenset({
    "class_declaration", "record_declaration", "enum_declaration",
})
_GO_TYPE_DECL: frozenset[str] = frozenset({"type_declaration"})


def _txt(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


@dataclass(frozen=True)
class TemporalCouplingIssue:
    line_number: int
    issue_type: str
    severity: str
    description: str
    reader_method: str
    writer_method: str
    variable_name: str

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
            "reader_method": self.reader_method,
            "writer_method": self.writer_method,
            "variable_name": self.variable_name,
        }


@dataclass
class MethodAccessInfo:
    name: str
    line: int = 0
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)


@dataclass
class TemporalCouplingResult:
    file_path: str
    total_classes: int = 0
    issues: list[TemporalCouplingIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_classes": self.total_classes,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


class TemporalCouplingAnalyzer(BaseAnalyzer):
    """Detects temporal coupling between methods in classes."""

    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go"}

    def analyze_file(self, file_path: str) -> TemporalCouplingResult:
        path = Path(file_path)
        if not path.exists():
            return TemporalCouplingResult(file_path=file_path)

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            return TemporalCouplingResult(file_path=file_path)

        language, parser = self._get_parser(extension)
        if language is None or parser is None:
            return TemporalCouplingResult(file_path=file_path)

        source = path.read_bytes()
        tree = parser.parse(source)
        return self._analyze(tree, source, file_path, extension)

    def _analyze(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        file_path: str,
        extension: str,
    ) -> TemporalCouplingResult:
        result = TemporalCouplingResult(file_path=file_path)

        if extension == ".py":
            self._analyze_python(tree, source, result)
        elif extension in (".js", ".jsx", ".ts", ".tsx"):
            self._analyze_js_ts(tree, source, result)
        elif extension == ".java":
            self._analyze_java(tree, source, result)
        elif extension == ".go":
            self._analyze_go(tree, source, result)

        return result

    # ── Python ──────────────────────────────────────────────────────

    def _analyze_python(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: TemporalCouplingResult,
    ) -> None:
        root = tree.root_node
        classes = self._collect_nodes(root, _PY_CLASS_TYPES)
        result.total_classes = len(classes)

        for cls in classes:
            methods = self._collect_python_methods(cls, source)
            self._detect_coupling(methods, result)

    def _collect_python_methods(
        self, class_node: tree_sitter.Node, source: bytes,
    ) -> list[MethodAccessInfo]:
        methods: list[MethodAccessInfo] = []
        body = class_node.child_by_field_name("body")
        if body is None:
            return methods

        for child in body.children:
            if child.type != "function_definition":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = _txt(name_node, source)
            info = MethodAccessInfo(
                name=method_name, line=child.start_point[0] + 1,
            )
            self._collect_python_accesses(child, source, info, is_write_context=False)
            methods.append(info)

        return methods

    def _collect_python_accesses(
        self,
        node: tree_sitter.Node,
        source: bytes,
        info: MethodAccessInfo,
        is_write_context: bool,
    ) -> None:
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_python_accesses(left, source, info, is_write_context=True)
            if right is not None:
                self._collect_python_accesses(right, source, info, is_write_context=False)
            return

        if node.type == "augmented_assignment":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_python_accesses(left, source, info, is_write_context=True)
                self._collect_python_accesses(left, source, info, is_write_context=False)
            if right is not None:
                self._collect_python_accesses(right, source, info, is_write_context=False)
            return

        if node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            if obj is not None and attr is not None:
                obj_text = _txt(obj, source)
                if obj_text == "self":
                    attr_name = _txt(attr, source)
                    if is_write_context:
                        info.writes.add(attr_name)
                    else:
                        info.reads.add(attr_name)
            return

        for child in node.children:
            self._collect_python_accesses(child, source, info, is_write_context)

    # ── JavaScript / TypeScript ─────────────────────────────────────

    def _analyze_js_ts(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: TemporalCouplingResult,
    ) -> None:
        root = tree.root_node
        classes = self._collect_nodes(root, _JS_CLASS_TYPES)
        result.total_classes = len(classes)

        for cls in classes:
            methods = self._collect_js_ts_methods(cls, source)
            self._detect_coupling(methods, result)

    def _collect_js_ts_methods(
        self, class_node: tree_sitter.Node, source: bytes,
    ) -> list[MethodAccessInfo]:
        methods: list[MethodAccessInfo] = []
        body = class_node.child_by_field_name("body")
        if body is None:
            return methods

        for child in body.children:
            if child.type not in ("method_definition", "public_field_definition"):
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = _txt(name_node, source)
            if method_name == "constructor":
                continue
            info = MethodAccessInfo(
                name=method_name, line=child.start_point[0] + 1,
            )
            self._collect_js_ts_accesses(child, source, info, is_write_context=False)
            methods.append(info)

        return methods

    def _collect_js_ts_accesses(
        self,
        node: tree_sitter.Node,
        source: bytes,
        info: MethodAccessInfo,
        is_write_context: bool,
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_js_ts_accesses(left, source, info, is_write_context=True)
            if right is not None:
                self._collect_js_ts_accesses(right, source, info, is_write_context=False)
            return

        if node.type in ("update_expression",):
            arg = node.child_by_field_name("argument")
            if arg is not None:
                self._collect_js_ts_accesses(arg, source, info, is_write_context=True)
                self._collect_js_ts_accesses(arg, source, info, is_write_context=False)
            return

        if node.type == "member_expression":
            obj = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            if obj is not None and prop is not None:
                obj_text = _txt(obj, source)
                if obj_text == "this":
                    prop_name = _txt(prop, source)
                    if is_write_context:
                        info.writes.add(prop_name)
                    else:
                        info.reads.add(prop_name)
                    return
            for child in node.children:
                self._collect_js_ts_accesses(child, source, info, is_write_context)
            return

        for child in node.children:
            self._collect_js_ts_accesses(child, source, info, is_write_context)

    # ── Java ────────────────────────────────────────────────────────

    def _analyze_java(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: TemporalCouplingResult,
    ) -> None:
        root = tree.root_node
        classes = self._collect_nodes(root, _JAVA_CLASS_TYPES)
        result.total_classes = len(classes)

        for cls in classes:
            methods = self._collect_java_methods(cls, source)
            self._detect_coupling(methods, result)

    def _collect_java_methods(
        self, class_node: tree_sitter.Node, source: bytes,
    ) -> list[MethodAccessInfo]:
        methods: list[MethodAccessInfo] = []
        body = class_node.child_by_field_name("body")
        if body is None:
            return methods

        for child in body.children:
            if child.type != "method_declaration":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            method_name = _txt(name_node, source)
            if method_node_is_java_constructor(child, source):
                continue
            info = MethodAccessInfo(
                name=method_name, line=child.start_point[0] + 1,
            )
            self._collect_java_accesses(child, source, info, is_write_context=False)
            methods.append(info)

        return methods

    def _collect_java_accesses(
        self,
        node: tree_sitter.Node,
        source: bytes,
        info: MethodAccessInfo,
        is_write_context: bool,
    ) -> None:
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_java_accesses(left, source, info, is_write_context=True)
            if right is not None:
                self._collect_java_accesses(right, source, info, is_write_context=False)
            return

        if node.type == "field_access":
            obj = node.child_by_field_name("object")
            field_node = node.child_by_field_name("field")
            if obj is not None and field_node is not None:
                obj_text = _txt(obj, source)
                if obj_text == "this":
                    field_name = _txt(field_node, source)
                    if is_write_context:
                        info.writes.add(field_name)
                    else:
                        info.reads.add(field_name)
            return

        for child in node.children:
            self._collect_java_accesses(child, source, info, is_write_context)

    # ── Go ──────────────────────────────────────────────────────────

    def _analyze_go(
        self,
        tree: tree_sitter.Tree,
        source: bytes,
        result: TemporalCouplingResult,
    ) -> None:
        root = tree.root_node
        receiver_methods = self._collect_go_receiver_methods(root, source)
        if not receiver_methods:
            return

        type_methods = _group_go_methods_by_type(receiver_methods)
        result.total_classes = len(type_methods)

        for _type_name, methods in type_methods.items():
            self._detect_coupling(methods, result)

    def _collect_go_receiver_methods(
        self, root: tree_sitter.Node, source: bytes,
    ) -> list[tuple[str, MethodAccessInfo]]:
        results: list[tuple[str, MethodAccessInfo]] = []
        self._walk_go_methods(root, source, results)
        return results

    def _walk_go_methods(
        self,
        node: tree_sitter.Node,
        source: bytes,
        results: list[tuple[str, MethodAccessInfo]],
    ) -> None:
        if node.type == "method_declaration":
            receiver = node.child_by_field_name("receiver")
            name_node = node.child_by_field_name("name")
            if receiver is not None and name_node is not None:
                type_name, receiver_var = self._extract_go_receiver(receiver, source)
                method_name = _txt(name_node, source)
                info = MethodAccessInfo(
                    name=method_name, line=node.start_point[0] + 1,
                )
                self._collect_go_accesses(
                    node, source, info, receiver_var, is_write_context=False,
                )
                results.append((type_name, info))

        for child in node.children:
            self._walk_go_methods(child, source, results)

    def _extract_go_receiver(
        self, receiver: tree_sitter.Node, source: bytes,
    ) -> tuple[str, str]:
        for child in receiver.children:
            if child.type == "parameter_declaration":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                var_name = _txt(name_node, source) if name_node is not None else ""
                type_name = _txt(type_node, source) if type_node is not None else ""
                type_name = type_name.lstrip("*")
                return type_name, var_name
        return "", ""

    def _collect_go_accesses(
        self,
        node: tree_sitter.Node,
        source: bytes,
        info: MethodAccessInfo,
        receiver_var: str,
        is_write_context: bool,
    ) -> None:
        if not receiver_var:
            return

        if node.type == "assignment_statement":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_go_accesses(
                    left, source, info, receiver_var, is_write_context=True,
                )
            if right is not None:
                self._collect_go_accesses(
                    right, source, info, receiver_var, is_write_context=False,
                )
            return

        if node.type in ("short_var_declaration", "var_spec"):
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._collect_go_accesses(
                    left, source, info, receiver_var, is_write_context=True,
                )
            if right is not None:
                self._collect_go_accesses(
                    right, source, info, receiver_var, is_write_context=False,
                )
            return

        if node.type == "selector_expression":
            operand = node.child_by_field_name("operand")
            field_node = node.child_by_field_name("field")
            if operand is not None and field_node is not None:
                operand_text = _txt(operand, source)
                if operand_text == receiver_var:
                    field_name = _txt(field_node, source)
                    if is_write_context:
                        info.writes.add(field_name)
                    else:
                        info.reads.add(field_name)
            return

        for child in node.children:
            self._collect_go_accesses(
                child, source, info, receiver_var, is_write_context,
            )

    # ── Coupling Detection ──────────────────────────────────────────

    def _detect_coupling(
        self, methods: list[MethodAccessInfo], result: TemporalCouplingResult,
    ) -> None:
        if len(methods) < 2:
            return

        write_map: dict[str, list[str]] = {}
        for m in methods:
            if m.name in _PY_INIT_NAMES:
                continue
            for var in m.writes:
                write_map.setdefault(var, []).append(m.name)

        for reader in methods:
            if reader.name in _PY_INIT_NAMES:
                continue
            for var in reader.reads:
                if var in reader.writes:
                    continue
                writers = write_map.get(var, [])
                if len(writers) == 1:
                    writer_name = writers[0]
                    if writer_name != reader.name:
                        result.issues.append(
                            TemporalCouplingIssue(
                                line_number=reader.line,
                                issue_type=ISSUE_TEMPORAL_COUPLING,
                                severity=_SEVERITY_MAP[ISSUE_TEMPORAL_COUPLING],
                                description=_DESCRIPTIONS[ISSUE_TEMPORAL_COUPLING],
                                reader_method=reader.name,
                                writer_method=writer_name,
                                variable_name=var,
                            )
                        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _collect_nodes(
        self, node: tree_sitter.Node, types: frozenset[str],
    ) -> list[tree_sitter.Node]:
        results: list[tree_sitter.Node] = []
        if node.type in types:
            results.append(node)
        for child in node.children:
            results.extend(self._collect_nodes(child, types))
        return results


def _group_go_methods_by_type(
    methods: list[tuple[str, MethodAccessInfo]],
) -> dict[str, list[MethodAccessInfo]]:
    groups: dict[str, list[MethodAccessInfo]] = {}
    for type_name, info in methods:
        if type_name:
            groups.setdefault(type_name, []).append(info)
    return groups


def method_node_is_java_constructor(
    node: tree_sitter.Node, source: bytes,
) -> bool:
    for child in node.children:
        if child.type == "identifier":
            method_name = _txt(child, source)
            ancestor = node.parent
            while ancestor is not None:
                if ancestor.type in _JAVA_CLASS_TYPES:
                    name_node = ancestor.child_by_field_name("name")
                    if name_node is not None:
                        class_name = _txt(name_node, source)
                        return method_name == class_name
                    break
                ancestor = ancestor.parent
    return False
