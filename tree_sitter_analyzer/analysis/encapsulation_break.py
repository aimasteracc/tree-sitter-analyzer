"""Encapsulation Break Detector.

Detects methods that return direct references to internal mutable state,
breaking encapsulation and allowing callers to corrupt object invariants.

Issues detected:
  - state_exposure: method returns a reference to internal mutable state
  - private_state_exposure: method returns a private mutable field

Supports Python, JavaScript/TypeScript, Java.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

ISSUE_STATE_EXPOSURE = "state_exposure"
ISSUE_PRIVATE_STATE_EXPOSURE = "private_state_exposure"

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_STATE_EXPOSURE: (
        "Method returns a direct reference to internal mutable state — "
        "callers can corrupt object invariants"
    ),
    ISSUE_PRIVATE_STATE_EXPOSURE: (
        "Method returns a direct reference to a private mutable field — "
        "consider returning a copy or read-only view"
    ),
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_STATE_EXPOSURE: (
        "Return a copy (list(), dict(), .copy()) or a read-only view "
        "(types.MappingProxyType, frozenset)"
    ),
    ISSUE_PRIVATE_STATE_EXPOSURE: (
        "Return a copy or use @property with a defensive copy"
    ),
}

_PY_MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset({
    "list", "dict", "set", "bytearray",
})

_PY_MUTABLE_LITERAL_TYPES: frozenset[str] = frozenset({
    "list", "dictionary", "set",
})

_PY_MUTABLE_COMPREHENSIONS: frozenset[str] = frozenset({
    "list_comprehension", "set_comprehension", "dictionary_comprehension",
})

_JS_MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset({
    "Map", "Set", "WeakMap", "WeakSet",
})

_JAVA_MUTABLE_TYPES: frozenset[str] = frozenset({
    "ArrayList", "HashMap", "HashSet", "LinkedList", "LinkedHashMap",
    "LinkedHashSet", "TreeMap", "TreeSet", "Vector", "Hashtable",
    "ArrayDeque", "PriorityQueue", "StringBuilder", "StringBuffer",
    "Properties",
})


def _txt(node: tree_sitter.Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


@dataclass(frozen=True)
class StateExposureIssue:
    line: int
    issue_type: str
    severity: str
    method_name: str
    field_name: str
    description: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "method_name": self.method_name,
            "field_name": self.field_name,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class EncapsulationBreakResult:
    file_path: str
    total_issues: int
    issues: tuple[StateExposureIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_issues": self.total_issues,
            "issues": [i.to_dict() for i in self.issues],
        }


class EncapsulationBreakAnalyzer(BaseAnalyzer):
    """Detects methods that return references to internal mutable state."""

    def __init__(self) -> None:
        super().__init__()
        self.SUPPORTED_EXTENSIONS = {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
        }

    def analyze_file(self, file_path: str | Path) -> EncapsulationBreakResult:
        path = Path(file_path)
        check = self._check_file(path)
        if check is None:
            return EncapsulationBreakResult(
                file_path=str(path), total_issues=0,
            )
        path, ext = check
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return EncapsulationBreakResult(
                file_path=str(path), total_issues=0,
            )

        source = path.read_bytes()
        tree = parser.parse(source)

        if ext == ".py":
            issues = self._analyze_python(tree.root_node, source)
        elif ext in {".js", ".jsx", ".ts", ".tsx"}:
            issues = self._analyze_js(tree.root_node, source)
        elif ext == ".java":
            issues = self._analyze_java(tree.root_node, source)
        else:
            issues = []

        return EncapsulationBreakResult(
            file_path=str(path),
            total_issues=len(issues),
            issues=tuple(issues),
        )

    # -- Python -----------------------------------------------------------

    def _analyze_python(
        self, root: tree_sitter.Node, source: bytes,
    ) -> list[StateExposureIssue]:
        issues: list[StateExposureIssue] = []
        for cls in self._find_nodes(root, "class_definition"):
            mutable = self._py_mutable_fields(cls, source)
            if not mutable:
                continue
            for method in self._py_methods(cls):
                self._py_check_returns(method, mutable, issues)
        return issues

    def _py_mutable_fields(
        self, cls: tree_sitter.Node, source: bytes,
    ) -> set[str]:
        fields: set[str] = set()
        for func in self._py_methods(cls):
            body = func.child_by_field_name("body")
            if not body:
                continue
            stack = [body]
            while stack:
                node = stack.pop()
                if node.type == "assignment":
                    left = node.child_by_field_name("left")
                    right = node.child_by_field_name("right")
                    if left and right and _txt(left).startswith("self."):
                        fname = _txt(left)[5:]
                        if self._py_is_mutable(right):
                            fields.add(fname)
                if node.type not in ("function_definition", "lambda"):
                    stack.extend(node.children)
        return fields

    def _py_is_mutable(self, node: tree_sitter.Node) -> bool:
        if node.type in _PY_MUTABLE_LITERAL_TYPES:
            return True
        if node.type in _PY_MUTABLE_COMPREHENSIONS:
            return True
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func and func.type == "identifier":
                if _txt(func) in _PY_MUTABLE_CONSTRUCTORS:
                    return True
        return False

    def _py_methods(
        self, cls: tree_sitter.Node,
    ) -> list[tree_sitter.Node]:
        methods: list[tree_sitter.Node] = []
        for child in cls.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        methods.append(stmt)
                    elif stmt.type == "decorated_definition":
                        for inner in stmt.children:
                            if inner.type == "function_definition":
                                methods.append(inner)
            elif child.type in ("function_definition",):
                methods.append(child)
        return methods

    def _py_check_returns(
        self,
        func: tree_sitter.Node,
        mutable: set[str],
        issues: list[StateExposureIssue],
    ) -> None:
        name_node = func.child_by_field_name("name")
        func_name = _txt(name_node) if name_node else "<anonymous>"
        body = func.child_by_field_name("body")
        if not body:
            return
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "return_statement":
                for child in node.children:
                    if child.type == "attribute":
                        obj = child.child_by_field_name("object")
                        attr = child.child_by_field_name("attribute")
                        if (
                            obj
                            and _txt(obj) == "self"
                            and attr
                            and _txt(attr) in mutable
                        ):
                            fname = _txt(attr)
                            private = fname.startswith("_")
                            itype = (
                                ISSUE_PRIVATE_STATE_EXPOSURE
                                if private
                                else ISSUE_STATE_EXPOSURE
                            )
                            issues.append(StateExposureIssue(
                                line=node.start_point[0] + 1,
                                issue_type=itype,
                                severity=SEVERITY_LOW if private else SEVERITY_MEDIUM,
                                method_name=func_name,
                                field_name=f"self.{fname}",
                                description=_DESCRIPTIONS[itype],
                                suggestion=_SUGGESTIONS[itype],
                            ))
            if node.type not in (
                "function_definition", "lambda", "class_definition",
            ):
                stack.extend(node.children)

    # -- JavaScript/TypeScript --------------------------------------------

    def _analyze_js(
        self, root: tree_sitter.Node, source: bytes,
    ) -> list[StateExposureIssue]:
        issues: list[StateExposureIssue] = []
        for cls in self._find_nodes(root, "class_declaration"):
            mutable = self._js_mutable_fields(cls)
            if not mutable:
                continue
            for method, name in self._js_methods(cls):
                self._js_check_returns(method, name, mutable, issues)
        return issues

    def _js_mutable_fields(self, cls: tree_sitter.Node) -> set[str]:
        fields: set[str] = set()
        body = self._get_class_body(cls)
        if not body:
            return fields
        for member in body.children:
            if member.type == "method_definition":
                mn = member.child_by_field_name("name")
                if mn and _txt(mn) == "constructor":
                    self._js_scan_assignments(member, fields)
            elif member.type in (
                "public_field_definition", "field_definition",
            ):
                val = member.child_by_field_name("value")
                nm = member.child_by_field_name("name")
                if val and nm and self._js_is_mutable(val):
                    fields.add(_txt(nm))
        return fields

    def _js_scan_assignments(
        self, func: tree_sitter.Node, fields: set[str],
    ) -> None:
        body = func.child_by_field_name("body")
        if not body:
            return
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                right = node.child_by_field_name("right")
                if (
                    left
                    and right
                    and _txt(left).startswith("this.")
                    and self._js_is_mutable(right)
                ):
                    fields.add(_txt(left)[5:])
            if node.type not in (
                "function_expression", "arrow_function",
                "function_declaration",
            ):
                stack.extend(node.children)

    def _js_is_mutable(self, node: tree_sitter.Node) -> bool:
        if node.type in ("array", "object"):
            return True
        if node.type == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor and _txt(ctor) in _JS_MUTABLE_CONSTRUCTORS:
                return True
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and _txt(func) in _JS_MUTABLE_CONSTRUCTORS:
                return True
        return False

    def _js_methods(
        self, cls: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        methods: list[tuple[tree_sitter.Node, str]] = []
        body = self._get_class_body(cls)
        if not body:
            return methods
        for member in body.children:
            if member.type == "method_definition":
                mn = member.child_by_field_name("name")
                methods.append((member, _txt(mn) if mn else "<anon>"))
            elif member.type in (
                "public_field_definition", "property_definition",
            ):
                for inner in member.children:
                    if inner.type == "arrow_function":
                        mn = member.child_by_field_name("name")
                        methods.append((inner, _txt(mn) if mn else "<anon>"))
        return methods

    def _js_check_returns(
        self,
        func: tree_sitter.Node,
        func_name: str,
        mutable: set[str],
        issues: list[StateExposureIssue],
    ) -> None:
        body = func.child_by_field_name("body")
        if not body:
            return
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "return_statement":
                for child in node.children:
                    if child.type == "member_expression":
                        obj = child.child_by_field_name("object")
                        prop = child.child_by_field_name("property")
                        if (
                            obj
                            and _txt(obj) == "this"
                            and prop
                            and _txt(prop) in mutable
                        ):
                            fname = _txt(prop)
                            private = fname.startswith("_")
                            itype = (
                                ISSUE_PRIVATE_STATE_EXPOSURE
                                if private
                                else ISSUE_STATE_EXPOSURE
                            )
                            issues.append(StateExposureIssue(
                                line=node.start_point[0] + 1,
                                issue_type=itype,
                                severity=SEVERITY_LOW if private else SEVERITY_MEDIUM,
                                method_name=func_name,
                                field_name=f"this.{fname}",
                                description=_DESCRIPTIONS[itype],
                                suggestion=_SUGGESTIONS[itype],
                            ))
            if node.type not in (
                "function_expression", "arrow_function",
                "function_declaration",
            ):
                stack.extend(node.children)

    # -- Java -------------------------------------------------------------

    def _analyze_java(
        self, root: tree_sitter.Node, source: bytes,
    ) -> list[StateExposureIssue]:
        issues: list[StateExposureIssue] = []
        for cls in self._find_nodes(root, "class_declaration"):
            mutable = self._java_mutable_fields(cls)
            if not mutable:
                continue
            for method, name in self._java_methods(cls):
                self._java_check_returns(method, name, mutable, issues)
        return issues

    def _java_mutable_fields(self, cls: tree_sitter.Node) -> set[str]:
        fields: set[str] = set()
        body = self._get_class_body(cls)
        if not body:
            return fields
        for member in body.children:
            if member.type != "field_declaration":
                continue
            for fc in member.children:
                type_text = _txt(fc)
                is_mutable = any(
                    type_text.startswith(mt) or type_text == mt
                    for mt in _JAVA_MUTABLE_TYPES
                )
                if is_mutable:
                    for vc in member.children:
                        if vc.type == "variable_declarator":
                            vn = vc.child_by_field_name("name")
                            if vn:
                                fields.add(_txt(vn))
        return fields

    def _java_methods(
        self, cls: tree_sitter.Node,
    ) -> list[tuple[tree_sitter.Node, str]]:
        methods: list[tuple[tree_sitter.Node, str]] = []
        body = self._get_class_body(cls)
        if not body:
            return methods
        for member in body.children:
            if member.type == "method_declaration":
                mn = member.child_by_field_name("name")
                methods.append((member, _txt(mn) if mn else "<anon>"))
        return methods

    def _java_check_returns(
        self,
        method: tree_sitter.Node,
        method_name: str,
        mutable: set[str],
        issues: list[StateExposureIssue],
    ) -> None:
        body = method.child_by_field_name("body")
        if not body:
            return
        stack = [body]
        while stack:
            node = stack.pop()
            if node.type == "return_statement":
                for child in node.children:
                    if child.type == "field_access":
                        obj = child.child_by_field_name("object")
                        fld = child.child_by_field_name("field")
                        if (
                            obj
                            and _txt(obj) == "this"
                            and fld
                            and _txt(fld) in mutable
                        ):
                            issues.append(StateExposureIssue(
                                line=node.start_point[0] + 1,
                                issue_type=ISSUE_STATE_EXPOSURE,
                                severity=SEVERITY_MEDIUM,
                                method_name=method_name,
                                field_name=f"this.{_txt(fld)}",
                                description=_DESCRIPTIONS[ISSUE_STATE_EXPOSURE],
                                suggestion=_SUGGESTIONS[ISSUE_STATE_EXPOSURE],
                            ))
            if node.type not in ("method_declaration", "class_declaration"):
                stack.extend(node.children)

    # -- Shared helpers ---------------------------------------------------

    @staticmethod
    def _find_nodes(
        root: tree_sitter.Node, node_type: str,
    ) -> list[tree_sitter.Node]:
        results: list[tree_sitter.Node] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == node_type:
                results.append(node)
            stack.extend(node.children)
        return results

    @staticmethod
    def _get_class_body(cls: tree_sitter.Node) -> tree_sitter.Node | None:
        for child in cls.children:
            if child.type == "class_body":
                return child
            if child.type == "body":
                return child
        return None
