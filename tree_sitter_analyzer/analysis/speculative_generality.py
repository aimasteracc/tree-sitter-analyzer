"""Speculative Generality Detector.

Detects over-abstracted code: abstract classes with few implementations,
unused type parameters, unused hook methods, and overly broad interfaces.

Issues detected:
  - speculative_abstract_class: abstract class/interface with 0-1 implementations
  - unused_type_parameter: generic param declared but never referenced in body
  - unused_hook: abstract/virtual method never overridden in subclass
  - overly_broad_interface: interface with 5+ abstract methods

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

ISSUE_SPECULATIVE_ABSTRACT = "speculative_abstract_class"
ISSUE_UNUSED_TYPE_PARAM = "unused_type_parameter"
ISSUE_UNUSED_HOOK = "unused_hook"
ISSUE_OVERLY_BROAD = "overly_broad_interface"

SEVERITY_MAP: dict[str, str] = {
    ISSUE_SPECULATIVE_ABSTRACT: SEVERITY_HIGH,
    ISSUE_UNUSED_TYPE_PARAM: SEVERITY_MEDIUM,
    ISSUE_UNUSED_HOOK: SEVERITY_MEDIUM,
    ISSUE_OVERLY_BROAD: SEVERITY_LOW,
}

DESCRIPTIONS: dict[str, str] = {
    ISSUE_SPECULATIVE_ABSTRACT: "Abstract class/interface has 0-1 implementations, suggesting premature abstraction",
    ISSUE_UNUSED_TYPE_PARAM: "Type parameter declared but never referenced in method bodies",
    ISSUE_UNUSED_HOOK: "Abstract/virtual method is never overridden in any subclass",
    ISSUE_OVERLY_BROAD: "Interface has many abstract methods, suggesting it should be split",
}

SUGGESTIONS: dict[str, str] = {
    ISSUE_SPECULATIVE_ABSTRACT: "Consider using a concrete class instead, or wait until you have 2+ implementations",
    ISSUE_UNUSED_TYPE_PARAM: "Remove the unused type parameter or use it in method signatures",
    ISSUE_UNUSED_HOOK: "Remove the unused abstract method or provide a default implementation",
    ISSUE_OVERLY_BROAD: "Split the interface into smaller, focused interfaces (ISP)",
}

BROAD_INTERFACE_THRESHOLD = 5

_ABSTRACT_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration", "interface_declaration"}),
    ".tsx": frozenset({"class_declaration", "interface_declaration"}),
    ".java": frozenset({"class_declaration", "interface_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

@dataclass(frozen=True)
class GeneralityIssue:
    """A single speculative generality issue."""

    issue_type: str
    line: int
    message: str
    severity: str
    name: str
    detail: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "name": self.name,
            "detail": self.detail,
        }

@dataclass(frozen=True)
class AbstractTypeInfo:
    """Information about an abstract type (class/interface)."""

    name: str
    start_line: int
    end_line: int
    is_abstract: bool
    parent_names: tuple[str, ...]
    abstract_methods: tuple[str, ...]
    type_params: tuple[str, ...]
    concrete_children: int

@dataclass(frozen=True)
class SpeculativeGeneralityResult:
    """Aggregated result of speculative generality analysis."""

    issues: tuple[GeneralityIssue, ...]
    abstract_types: tuple[AbstractTypeInfo, ...]
    total_types: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(self, severity: str) -> list[GeneralityIssue]:
        return [i for i in self.issues if i.severity == severity]

    def get_issues_by_type(self, issue_type: str) -> list[GeneralityIssue]:
        return [i for i in self.issues if i.issue_type == issue_type]

    def to_dict(self) -> dict[str, object]:
        return {
            "file_path": self.file_path,
            "total_types": self.total_types,
            "total_issues": self.total_issues,
            "high_severity_count": self.high_severity_count,
            "issues": [i.to_dict() for i in self.issues],
        }

class SpeculativeGeneralityAnalyzer(BaseAnalyzer):
    """Detects speculative generality: premature abstractions and over-engineering."""

    def __init__(self, broad_threshold: int = BROAD_INTERFACE_THRESHOLD) -> None:
        self._broad_threshold = broad_threshold
        super().__init__()

    def analyze_file(self, file_path: Path | str) -> SpeculativeGeneralityResult:
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

        if ext == ".py":
            types_info = self._extract_python_types(tree.root_node, content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            types_info = self._extract_js_types(tree.root_node, content, ext)
        elif ext == ".java":
            types_info = self._extract_java_types(tree.root_node, content)
        elif ext == ".go":
            types_info = self._extract_go_types(tree.root_node, content)
        else:
            types_info = []

        name_to_type = {t.name: t for t in types_info}
        issues = self._detect_issues(types_info, name_to_type, content)

        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)

        return SpeculativeGeneralityResult(
            issues=tuple(issues),
            abstract_types=tuple(types_info),
            total_types=len(types_info),
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=str(path),
        )

    def _empty_result(self, file_path: str) -> SpeculativeGeneralityResult:
        return SpeculativeGeneralityResult(
            issues=(),
            abstract_types=(),
            total_types=0,
            total_issues=0,
            high_severity_count=0,
            file_path=file_path,
        )

    def _count_concrete_children(
        self,
        type_info: AbstractTypeInfo,
        name_to_type: dict[str, AbstractTypeInfo],
    ) -> int:
        count = 0
        for other in name_to_type.values():
            if other.name == type_info.name:
                continue
            if type_info.name in other.parent_names and not other.is_abstract:
                count += 1
        return count

    def _count_go_implementations(
        self,
        type_info: AbstractTypeInfo,
        name_to_type: dict[str, AbstractTypeInfo],
        content: bytes,
    ) -> int:
        if not type_info.abstract_methods:
            return 0
        count = 0
        text = content.decode("utf-8", errors="replace")
        for other in name_to_type.values():
            if other.is_abstract or other.name == type_info.name:
                continue
            all_methods_found = True
            for method_name in type_info.abstract_methods:
                if f") {method_name}(" not in text:
                    all_methods_found = False
                    break
            if all_methods_found:
                count += 1
        return count

    def _find_overridden_methods(
        self,
        abstract_methods: tuple[str, ...],
        name_to_type: dict[str, AbstractTypeInfo],
        parent_name: str,
        content: bytes,
    ) -> set[str]:
        overridden: set[str] = set()
        lines = content.decode("utf-8", errors="replace").split("\n")
        for other in name_to_type.values():
            if other.name == parent_name:
                continue
            if parent_name in other.parent_names:
                # Get text from subclass line range
                start = max(0, other.start_line - 1)
                end = min(len(lines), other.end_line)
                subclass_text = "\n".join(lines[start:end])
                for method_name in abstract_methods:
                    if method_name in overridden:
                        continue
                    if self._method_exists_in_range(method_name, subclass_text):
                        overridden.add(method_name)
        return overridden

    def _method_exists_in_range(self, method_name: str, text: str) -> bool:
        # Python: def method_name
        if f"def {method_name}" in text:
            return True
        # JS/TS: method_name( in class body
        if f"{method_name}(" in text:
            return True
        # Go: func (...) method_name(
        if f") {method_name}(" in text:
            return True
        return False

    def _detect_issues(
        self,
        types_info: list[AbstractTypeInfo],
        name_to_type: dict[str, AbstractTypeInfo],
        content: bytes,
    ) -> list[GeneralityIssue]:
        issues: list[GeneralityIssue] = []

        for type_info in types_info:
            # Check for speculative abstract class
            if type_info.is_abstract:
                concrete_count = self._count_concrete_children(
                    type_info, name_to_type
                )
                # For Go: also check method-based implementation detection
                # (Go uses structural typing, no explicit implements)
                go_count = self._count_go_implementations(
                    type_info, name_to_type, content
                )
                concrete_count = max(concrete_count, go_count)
                if concrete_count <= 1:
                    label = "no implementations" if concrete_count == 0 else "only 1 implementation"
                    issues.append(GeneralityIssue(
                        issue_type=ISSUE_SPECULATIVE_ABSTRACT,
                        line=type_info.start_line,
                        message=f"Abstract type '{type_info.name}' has {label}",
                        severity=SEVERITY_MAP[ISSUE_SPECULATIVE_ABSTRACT],
                        name=type_info.name,
                        detail=SUGGESTIONS[ISSUE_SPECULATIVE_ABSTRACT],
                    ))

                # Check for overly broad interface
                if len(type_info.abstract_methods) >= self._broad_threshold:
                    issues.append(GeneralityIssue(
                        issue_type=ISSUE_OVERLY_BROAD,
                        line=type_info.start_line,
                        message=f"Abstract type '{type_info.name}' has {len(type_info.abstract_methods)} abstract methods (threshold: {self._broad_threshold})",
                        severity=SEVERITY_MAP[ISSUE_OVERLY_BROAD],
                        name=type_info.name,
                        detail=SUGGESTIONS[ISSUE_OVERLY_BROAD],
                    ))

                # Check for unused hook methods (only when there ARE implementations)
                if type_info.abstract_methods and concrete_count >= 2:
                    overridden = self._find_overridden_methods(
                        type_info.abstract_methods, name_to_type, type_info.name,
                        content,
                    )
                    for method_name in type_info.abstract_methods:
                        if method_name not in overridden:
                            issues.append(GeneralityIssue(
                                issue_type=ISSUE_UNUSED_HOOK,
                                line=type_info.start_line,
                                message=f"Abstract method '{method_name}' on '{type_info.name}' is never overridden",
                                severity=SEVERITY_MAP[ISSUE_UNUSED_HOOK],
                                name=type_info.name,
                                detail=SUGGESTIONS[ISSUE_UNUSED_HOOK],
                            ))

            # Check for unused type parameters
            if type_info.type_params:
                used_params = self._find_used_type_params(
                    type_info, content
                )
                for param in type_info.type_params:
                    if param not in used_params:
                        issues.append(GeneralityIssue(
                            issue_type=ISSUE_UNUSED_TYPE_PARAM,
                            line=type_info.start_line,
                            message=f"Type parameter '{param}' on '{type_info.name}' is never used",
                            severity=SEVERITY_MAP[ISSUE_UNUSED_TYPE_PARAM],
                            name=type_info.name,
                            detail=SUGGESTIONS[ISSUE_UNUSED_TYPE_PARAM],
                        ))

        return issues

    def _find_used_type_params(
        self, type_info: AbstractTypeInfo, content: bytes
    ) -> set[str]:
        text = content.decode("utf-8", errors="replace")
        start = content.decode("utf-8", errors="replace").find(
            content[
                :100
            ].decode("utf-8", errors="replace")
        )
        if start < 0:
            start = 0
        used: set[str] = set()
        for param in type_info.type_params:
            # Check if param name appears in the class body (beyond its declaration)
            search_text = text[type_info.start_line:]
            count = search_text.count(param)
            if count > 1:  # More than just the declaration
                used.add(param)
        return used

    # ── Python ────────────────────────────────────────────────────────────

    def _extract_python_types(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[AbstractTypeInfo]:
        types_info: list[AbstractTypeInfo] = []
        self._walk_python_types(root, content, types_info)
        return types_info

    def _walk_python_types(
        self,
        node: tree_sitter.Node,
        content: bytes,
        types_info: list[AbstractTypeInfo],
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type == "class_definition":
                    info = self._parse_python_type(child, content)
                    if info is not None:
                        types_info.append(info)
            return

        if node.type == "class_definition":
            info = self._parse_python_type(node, content)
            if info is not None:
                types_info.append(info)

        for child in node.children:
            self._walk_python_types(child, content, types_info)

    def _parse_python_type(
        self, node: tree_sitter.Node, content: bytes
    ) -> AbstractTypeInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        # Check for ABC base or abstract methods
        is_abstract = self._is_python_abstract(node, content)
        parent_names = self._get_python_parents(node, content)
        abstract_methods = self._get_python_abstract_methods(node, content)
        type_params = self._get_python_type_params(node, content)

        return AbstractTypeInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=is_abstract,
            parent_names=tuple(parent_names),
            abstract_methods=tuple(abstract_methods),
            type_params=tuple(type_params),
            concrete_children=0,
        )

    def _is_python_abstract(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        # Check if class inherits from ABC or has abstract methods
        arg_list = node.child_by_field_name("superclasses")
        if arg_list:
            text = content[arg_list.start_byte:arg_list.end_byte].decode(
                "utf-8", errors="replace"
            )
            if "ABC" in text or "abc.ABC" in text:
                return True

        # Check body for @abstractmethod decorated methods
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "decorated_definition":
                    for dec_child in child.children:
                        if dec_child.type == "decorator":
                            dec_text = content[
                                dec_child.start_byte:dec_child.end_byte
                            ].decode("utf-8", errors="replace")
                            if "abstractmethod" in dec_text:
                                return True
        return False

    def _get_python_parents(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        parent_names: list[str] = []
        arg_list = node.child_by_field_name("superclasses")
        if arg_list:
            for child in arg_list.children:
                if child.type in ("identifier", "attribute"):
                    parent_names.append(
                        content[child.start_byte:child.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )
        return parent_names

    def _get_python_abstract_methods(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        methods: list[str] = []
        body = node.child_by_field_name("body")
        if not body:
            return methods

        for child in body.children:
            if child.type == "decorated_definition":
                is_abstract = False
                method_name = ""
                for dec_child in child.children:
                    if dec_child.type == "decorator":
                        dec_text = content[
                            dec_child.start_byte:dec_child.end_byte
                        ].decode("utf-8", errors="replace")
                        if "abstractmethod" in dec_text:
                            is_abstract = True
                    if dec_child.type == "function_definition":
                        name_node = dec_child.child_by_field_name("name")
                        if name_node:
                            method_name = content[
                                name_node.start_byte:name_node.end_byte
                            ].decode("utf-8", errors="replace")
                if is_abstract and method_name:
                    methods.append(method_name)
        return methods

    def _get_python_type_params(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        # Python 3.12+ type_params field on class_definition
        params: list[str] = []
        tp_node = node.child_by_field_name("type_params")
        if tp_node:
            for child in tp_node.children:
                if child.type == "type_parameter":
                    name_text = content[
                        child.start_byte:child.end_byte
                    ].decode("utf-8", errors="replace")
                    params.append(name_text.strip())
        return params

    # ── JavaScript / TypeScript ───────────────────────────────────────────

    def _extract_js_types(
        self,
        root: tree_sitter.Node,
        content: bytes,
        ext: str,
    ) -> list[AbstractTypeInfo]:
        types_info: list[AbstractTypeInfo] = []
        self._walk_js_types(root, content, ext, types_info)
        return types_info

    def _walk_js_types(
        self,
        node: tree_sitter.Node,
        content: bytes,
        ext: str,
        types_info: list[AbstractTypeInfo],
    ) -> None:
        if node.type in ("class_declaration", "class_expression", "abstract_class_declaration"):
            info = self._parse_js_class(node, content)
            if info is not None:
                types_info.append(info)

        if ext in (".ts", ".tsx") and node.type == "interface_declaration":
            info = self._parse_ts_interface(node, content)
            if info is not None:
                types_info.append(info)

        for child in node.children:
            self._walk_js_types(child, content, ext, types_info)

    def _parse_js_class(
        self, node: tree_sitter.Node, content: bytes
    ) -> AbstractTypeInfo | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        is_abstract = node.type == "abstract_class_declaration"
        if not is_abstract:
            for child in node.children:
                if child.type == "abstract_modifier":
                    is_abstract = True
                    break
                # Check for abstract in class heritage (TS syntax)
                if child.type in ("class_heritage",):
                    continue
                text = content[child.start_byte:child.end_byte].decode(
                    "utf-8", errors="replace"
                )
                if child.type in ("identifier", "class", "property_identifier"):
                    continue
                if "abstract" in text and child.type not in ("class_body", "method_definition", "public_field_definition"):
                    is_abstract = True
                    break

        parent_names: list[str] = []
        for child in node.children:
            if child.type == "class_heritage":
                for sub in child.children:
                    if sub.type == "identifier":
                        parent_names.append(
                            content[sub.start_byte:sub.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
                    elif sub.type == "implements_clause":
                        for impl_sub in sub.children:
                            if impl_sub.type == "type_identifier":
                                parent_names.append(
                                    content[impl_sub.start_byte:impl_sub.end_byte].decode(
                                        "utf-8", errors="replace"
                                    )
                                )
                    elif sub.type in ("extends_clause", "call_expression"):
                        for ext_sub in sub.children:
                            if ext_sub.type == "identifier":
                                parent_names.append(
                                    content[ext_sub.start_byte:ext_sub.end_byte].decode(
                                        "utf-8", errors="replace"
                                    )
                                )

        abstract_methods = self._get_js_abstract_methods(node, content)
        type_params = self._get_js_type_params(node, content)

        return AbstractTypeInfo(
            name=name or "<anonymous>",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=is_abstract,
            parent_names=tuple(parent_names),
            abstract_methods=tuple(abstract_methods),
            type_params=tuple(type_params),
            concrete_children=0,
        )

    def _parse_ts_interface(
        self, node: tree_sitter.Node, content: bytes
    ) -> AbstractTypeInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        abstract_methods = self._get_ts_interface_methods(node, content)
        type_params = self._get_js_type_params(node, content)

        return AbstractTypeInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=True,  # interfaces are inherently abstract
            parent_names=(),
            abstract_methods=tuple(abstract_methods),
            type_params=tuple(type_params),
            concrete_children=0,
        )

    def _get_js_abstract_methods(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        methods: list[str] = []
        body = node.child_by_field_name("body")
        if not body:
            return methods

        for child in body.children:
            if child.type == "method_definition":
                is_abstract = False
                for sub in child.children:
                    if sub.type == "abstract_modifier":
                        is_abstract = True
                        break
                    text = content[sub.start_byte:sub.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    if "abstract" in text:
                        is_abstract = True
                        break
                if is_abstract:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        methods.append(
                            content[name_node.start_byte:name_node.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
            elif child.type == "abstract_method_signature":
                name_node = child.child_by_field_name("name")
                if name_node:
                    methods.append(
                        content[name_node.start_byte:name_node.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )
            elif child.type == "public_field_definition":
                # Abstract property
                is_abstract = False
                for sub in child.children:
                    text = content[sub.start_byte:sub.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    if "abstract" in text:
                        is_abstract = True
                        break
                if is_abstract:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        methods.append(
                            content[name_node.start_byte:name_node.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
        return methods

    def _get_ts_interface_methods(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        methods: list[str] = []
        body = node.child_by_field_name("body")
        if not body:
            return methods

        for child in body.children:
            if child.type in ("method_signature", "property_signature"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    methods.append(
                        content[name_node.start_byte:name_node.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )
        return methods

    def _get_js_type_params(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        params: list[str] = []
        for child in node.children:
            if child.type == "type_parameters":
                for tp in child.children:
                    if tp.type == "type_parameter":
                        name_node = tp.child_by_field_name("name")
                        if name_node:
                            params.append(
                                content[
                                    name_node.start_byte:name_node.end_byte
                                ].decode("utf-8", errors="replace")
                            )
        return params

    # ── Java ──────────────────────────────────────────────────────────────

    def _extract_java_types(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[AbstractTypeInfo]:
        types_info: list[AbstractTypeInfo] = []
        self._walk_java_types(root, content, types_info)
        return types_info

    def _walk_java_types(
        self,
        node: tree_sitter.Node,
        content: bytes,
        types_info: list[AbstractTypeInfo],
    ) -> None:
        if node.type in (
            "class_declaration",
            "interface_declaration",
        ):
            info = self._parse_java_type(node, content)
            if info is not None:
                types_info.append(info)

        for child in node.children:
            self._walk_java_types(child, content, types_info)

    def _parse_java_type(
        self, node: tree_sitter.Node, content: bytes
    ) -> AbstractTypeInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        is_abstract = False
        is_interface = node.type == "interface_declaration"
        if is_interface:
            is_abstract = True
        else:
            is_abstract = self._java_has_abstract_modifier(node, content)

        parent_names: list[str] = []
        extends_node = node.child_by_field_name("superclass")
        if extends_node:
            self._collect_java_type_identifiers(extends_node, content, parent_names)

        implements_node = node.child_by_field_name("interfaces")
        if not implements_node:
            implements_node = node.child_by_field_name("implements")
        if implements_node:
            self._collect_java_type_identifiers(implements_node, content, parent_names)

        abstract_methods = self._get_java_abstract_methods(node, content, is_interface)
        type_params = self._get_java_type_params(node, content)

        return AbstractTypeInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=is_abstract,
            parent_names=tuple(parent_names),
            abstract_methods=tuple(abstract_methods),
            type_params=tuple(type_params),
            concrete_children=0,
        )

    def _java_has_abstract_modifier(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "abstract":
                        return True
            elif child.type == "abstract":
                return True
        return False

    def _collect_java_type_identifiers(
        self, node: tree_sitter.Node, content: bytes, names: list[str]
    ) -> None:
        for child in node.children:
            if child.type == "type_identifier":
                names.append(
                    content[child.start_byte:child.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                )
            elif child.type not in ("implements", "extends"):
                self._collect_java_type_identifiers(child, content, names)

    def _get_java_abstract_methods(
        self,
        node: tree_sitter.Node,
        content: bytes,
        is_interface: bool,
    ) -> list[str]:
        methods: list[str] = []
        body = node.child_by_field_name("body")
        if not body:
            return methods

        for child in body.children:
            if child.type == "method_declaration":
                has_abstract = is_interface  # interface methods are implicitly abstract
                if not has_abstract:
                    for modifier in child.children:
                        if modifier.type == "modifiers":
                            for sub in modifier.children:
                                if sub.type == "abstract":
                                    has_abstract = True
                                    break
                        if modifier.type == "abstract":
                            has_abstract = True
                            break

                if has_abstract:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        methods.append(
                            content[name_node.start_byte:name_node.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                        )
            elif child.type == "interface_declaration":
                # Nested interface
                pass
        return methods

    def _get_java_type_params(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        params: list[str] = []
        for child in node.children:
            if child.type == "type_parameters":
                for tp in child.children:
                    if tp.type == "type_parameter":
                        name_text = content[
                            tp.start_byte:tp.end_byte
                        ].decode("utf-8", errors="replace")
                        params.append(name_text.strip())
        return params

    # ── Go ────────────────────────────────────────────────────────────────

    def _extract_go_types(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[AbstractTypeInfo]:
        types_info: list[AbstractTypeInfo] = []
        self._walk_go_types(root, content, types_info)
        return types_info

    def _walk_go_types(
        self,
        node: tree_sitter.Node,
        content: bytes,
        types_info: list[AbstractTypeInfo],
    ) -> None:
        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    info = self._parse_go_type_spec(child, content)
                    if info is not None:
                        types_info.append(info)

        for child in node.children:
            self._walk_go_types(child, content, types_info)

    def _parse_go_type_spec(
        self, node: tree_sitter.Node, content: bytes
    ) -> AbstractTypeInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        type_node = node.child_by_field_name("type")
        is_interface = False
        abstract_methods: list[str] = []

        if type_node and type_node.type == "interface_type":
            is_interface = True
            for child in type_node.children:
                if child.type in ("method_spec", "method_elem"):
                    name_text = content[
                        child.start_byte:child.end_byte
                    ].decode("utf-8", errors="replace")
                    paren_idx = name_text.find("(")
                    if paren_idx > 0:
                        abstract_methods.append(name_text[:paren_idx].strip())
                    else:
                        abstract_methods.append(name_text.strip())

        type_params = self._get_go_type_params(node, content)

        return AbstractTypeInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            is_abstract=is_interface,  # In Go, interfaces are the abstract types
            parent_names=(),
            abstract_methods=tuple(abstract_methods),
            type_params=tuple(type_params),
            concrete_children=0,
        )

    def _get_go_type_params(
        self, node: tree_sitter.Node, content: bytes
    ) -> list[str]:
        # Go 1.18+ type parameters
        params: list[str] = []
        for child in node.children:
            if child.type == "type_parameter_list":
                for tp in child.children:
                    if tp.type == "type_parameter":
                        name_text = content[
                            tp.start_byte:tp.end_byte
                        ].decode("utf-8", errors="replace")
                        params.append(name_text.strip())
        return params
