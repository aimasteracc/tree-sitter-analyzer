"""
Inheritance Quality Analyzer.

Detects inheritance anti-patterns: deep hierarchies, missing super() calls,
diamond inheritance, and empty overrides. Pure AST analysis, no runtime deps.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_INFO = "info"

DEFAULT_DEPTH_THRESHOLD = 3


@dataclass(frozen=True)
class InheritanceIssue:
    """A single inheritance quality issue."""

    issue_type: str
    line: int
    message: str
    severity: str
    class_name: str
    detail: str


@dataclass(frozen=True)
class ClassInfo:
    """Information about a class found during analysis."""

    name: str
    start_line: int
    end_line: int
    parent_names: tuple[str, ...]
    depth: int
    has_init: bool
    has_super_call: bool
    methods: tuple[MethodInfo, ...]


@dataclass(frozen=True)
class MethodInfo:
    """Information about a method in a class."""

    name: str
    start_line: int
    end_line: int
    body_text: str
    calls_super_only: bool


@dataclass(frozen=True)
class InheritanceQualityResult:
    """Aggregated result of inheritance quality analysis."""

    issues: tuple[InheritanceIssue, ...]
    classes: tuple[ClassInfo, ...]
    total_classes: int
    total_issues: int
    high_severity_count: int
    file_path: str

    def get_issues_by_severity(self, severity: str) -> list[InheritanceIssue]:
        return [i for i in self.issues if i.severity == severity]

    def get_issues_by_type(self, issue_type: str) -> list[InheritanceIssue]:
        return [i for i in self.issues if i.issue_type == issue_type]


class InheritanceQualityAnalyzer:
    """Analyzes inheritance quality patterns in source code."""

    def __init__(self, depth_threshold: int = DEFAULT_DEPTH_THRESHOLD) -> None:
        self._depth_threshold = depth_threshold
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(
        self, extension: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if extension not in _LANGUAGE_MODULES:
            return None, None
        if extension not in self._parsers:
            module_name = _LANGUAGE_MODULES[extension]
            try:
                lang_module = __import__(module_name)
                func_name = _LANGUAGE_FUNCS.get(extension, "language")
                language_func = getattr(lang_module, func_name)
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None
        return self._languages.get(extension), self._parsers.get(extension)

    def analyze_file(self, file_path: Path | str) -> InheritanceQualityResult:
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
            classes = self._extract_python_classes(tree.root_node, content)
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            classes = self._extract_js_classes(tree.root_node, content)
        elif ext == ".java":
            classes = self._extract_java_classes(tree.root_node, content)
        elif ext == ".go":
            classes = self._extract_go_structs(tree.root_node, content)
        else:
            classes = []

        depth_map = self._build_depth_map(classes)
        issues = self._detect_issues(classes, depth_map)

        high_count = sum(1 for i in issues if i.severity == SEVERITY_HIGH)

        return InheritanceQualityResult(
            issues=tuple(issues),
            classes=tuple(classes),
            total_classes=len(classes),
            total_issues=len(issues),
            high_severity_count=high_count,
            file_path=str(path),
        )

    def _empty_result(self, file_path: str) -> InheritanceQualityResult:
        return InheritanceQualityResult(
            issues=(),
            classes=(),
            total_classes=0,
            total_issues=0,
            high_severity_count=0,
            file_path=file_path,
        )

    def _build_depth_map(self, classes: list[ClassInfo]) -> dict[str, int]:
        depth_map: dict[str, int] = {}
        remaining = list(classes)
        max_iterations = len(remaining) * 2 + 1
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            resolved: list[int] = []
            for idx, cls in enumerate(remaining):
                if not cls.parent_names:
                    depth_map[cls.name] = 1
                    resolved.append(idx)
                elif all(
                    p in depth_map or p == "object" or p == "Object"
                    for p in cls.parent_names
                ):
                    parent_depths = [
                        depth_map.get(p, 0) if p not in ("object", "Object") else 0
                        for p in cls.parent_names
                    ]
                    depth_map[cls.name] = max(parent_depths) + 1
                    resolved.append(idx)

            for idx in reversed(resolved):
                remaining.pop(idx)

        for cls in remaining:
            depth_map[cls.name] = 1

        return depth_map

    def _detect_issues(
        self,
        classes: list[ClassInfo],
        depth_map: dict[str, int],
    ) -> list[InheritanceIssue]:
        issues: list[InheritanceIssue] = []

        for cls in classes:
            depth = depth_map.get(cls.name, 1)

            if depth > self._depth_threshold:
                chain = self._build_chain(cls, classes)
                issues.append(InheritanceIssue(
                    issue_type="deep_inheritance",
                    line=cls.start_line,
                    message=f"Class '{cls.name}' has inheritance depth {depth} (threshold: {self._depth_threshold})",
                    severity=SEVERITY_HIGH,
                    class_name=cls.name,
                    detail=f"Chain: {' -> '.join(chain)}",
                ))

            if cls.has_init and not cls.has_super_call and cls.parent_names:
                non_object_parents = [
                    p for p in cls.parent_names
                    if p not in ("object", "Object")
                ]
                if non_object_parents:
                    issues.append(InheritanceIssue(
                        issue_type="missing_super_call",
                        line=cls.start_line,
                        message=f"Class '{cls.name}' __init__ does not call super().__init__()",
                        severity=SEVERITY_MEDIUM,
                        class_name=cls.name,
                        detail=f"Parents: {', '.join(non_object_parents)}",
                    ))

            if len(cls.parent_names) >= 2:
                issues.append(InheritanceIssue(
                    issue_type="diamond_inheritance",
                    line=cls.start_line,
                    message=f"Class '{cls.name}' uses multiple inheritance",
                    severity=SEVERITY_INFO,
                    class_name=cls.name,
                    detail=f"Parents: {', '.join(cls.parent_names)}",
                ))

            for method in cls.methods:
                if method.calls_super_only and cls.parent_names:
                    issues.append(InheritanceIssue(
                        issue_type="empty_override",
                        line=method.start_line,
                        message=f"Method '{cls.name}.{method.name}' only calls super() with no additional logic",
                        severity=SEVERITY_INFO,
                        class_name=cls.name,
                        detail="Consider removing if behavior is identical to parent",
                    ))

        return issues

    def _build_chain(
        self, cls: ClassInfo, classes: list[ClassInfo]
    ) -> list[str]:
        name_to_class = {c.name: c for c in classes}
        chain: list[str] = [cls.name]
        current = cls
        visited: set[str] = {cls.name}
        while current.parent_names:
            parent_name = current.parent_names[0]
            if parent_name in ("object", "Object") or parent_name in visited:
                break
            chain.append(parent_name)
            visited.add(parent_name)
            current = name_to_class.get(parent_name, ClassInfo(
                name=parent_name, start_line=0, end_line=0,
                parent_names=(), depth=1, has_init=False,
                has_super_call=False, methods=(),
            ))
        return chain

    # ── Python ────────────────────────────────────────────────────────────

    def _extract_python_classes(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[ClassInfo]:
        classes: list[ClassInfo] = []
        self._walk_python_classes(root, content, classes)
        return classes

    def _walk_python_classes(
        self,
        node: tree_sitter.Node,
        content: bytes,
        classes: list[ClassInfo],
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type == "class_definition":
                    cls = self._parse_python_class(child, content)
                    if cls is not None:
                        classes.append(cls)
            return

        if node.type == "class_definition":
            cls = self._parse_python_class(node, content)
            if cls is not None:
                classes.append(cls)

        for child in node.children:
            self._walk_python_classes(child, content, classes)

    def _parse_python_class(
        self, node: tree_sitter.Node, content: bytes
    ) -> ClassInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        arg_list = node.child_by_field_name("superclasses")
        parent_names: list[str] = []
        if arg_list:
            for child in arg_list.children:
                if child.type in ("identifier", "attribute", "keyword_argument"):
                    parent_names.append(
                        content[child.start_byte:child.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )

        body = node.child_by_field_name("body")
        has_init = False
        has_super_call = False
        methods: list[MethodInfo] = []

        if body:
            for child in body.children:
                if child.type == "decorated_definition":
                    for dec_child in child.children:
                        if dec_child.type == "function_definition":
                            m = self._parse_python_method(dec_child, content)
                            if m.name == "__init__":
                                has_init = True
                                has_super_call = m.calls_super_only or self._has_super_in_body(child, content)
                            methods.append(m)
                elif child.type == "function_definition":
                    m = self._parse_python_method(child, content)
                    if m.name == "__init__":
                        has_init = True
                        has_super_call = self._has_super_in_body(child, content)
                    methods.append(m)

        return ClassInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent_names=tuple(parent_names),
            depth=1,
            has_init=has_init,
            has_super_call=has_super_call,
            methods=tuple(methods),
        )

    def _has_super_in_body(
        self, node: tree_sitter.Node, content: bytes
    ) -> bool:
        body = node.child_by_field_name("body")
        if not body:
            return False
        return self._contains_super_call(body)

    def _contains_super_call(self, node: tree_sitter.Node) -> bool:
        if node.type in ("call_expression", "call", "method_invocation"):
            if self._is_super_call(node):
                return True

        for child in node.children:
            if self._contains_super_call(child):
                return True
        return False

    def _is_super_call(self, node: tree_sitter.Node) -> bool:
        # Java: method_invocation with "super" field
        if node.type == "method_invocation":
            super_node = node.child_by_field_name("object")
            if super_node and super_node.type == "super":
                return True
            for child in node.children:
                if child.type == "super":
                    return True
            return False

        func = node.child_by_field_name("function")
        if not func:
            return False

        if func.type in ("attribute", "member_expression"):
            obj = func.child_by_field_name("object")
            if obj and obj.type in ("call_expression", "call"):
                inner_func = obj.child_by_field_name("function")
                if inner_func and inner_func.type == "identifier":
                    text = inner_func.text
                    if text and text.decode("utf-8", errors="replace") == "super":
                        return True
        elif func.type == "identifier":
            text = func.text
            if text and text.decode("utf-8", errors="replace") == "super":
                return True

        return False

    def _parse_python_method(
        self, node: tree_sitter.Node, content: bytes
    ) -> MethodInfo:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        body = node.child_by_field_name("body")
        body_text = ""
        calls_super_only = False

        if body:
            body_text = content[body.start_byte:body.end_byte].decode(
                "utf-8", errors="replace"
            )
            calls_super_only = self._is_super_only_body(body, content)

        return MethodInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            body_text=body_text,
            calls_super_only=calls_super_only,
        )

    _TRIVIAL_NODE_TYPES: frozenset[str] = frozenset({
        "pass_statement", "comment", "{", "}", ";",
    })

    def _is_super_only_body(
        self, body: tree_sitter.Node, content: bytes
    ) -> bool:
        super_stmts = [
            c for c in body.children
            if c.type == "expression_statement" and self._is_super_stmt(c)
        ]
        non_trivial = [
            c for c in body.children
            if c.type not in self._TRIVIAL_NODE_TYPES
        ]
        return len(super_stmts) > 0 and len(non_trivial) == len(super_stmts)

    def _is_super_stmt(self, node: tree_sitter.Node) -> bool:
        for child in node.children:
            if child.type in ("call_expression", "call", "method_invocation") and self._is_super_call(child):
                return True
        return False

    # ── JavaScript / TypeScript ───────────────────────────────────────────

    def _extract_js_classes(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[ClassInfo]:
        classes: list[ClassInfo] = []
        self._walk_js_classes(root, content, classes)
        return classes

    def _walk_js_classes(
        self,
        node: tree_sitter.Node,
        content: bytes,
        classes: list[ClassInfo],
    ) -> None:
        if node.type in ("class_declaration", "class_expression"):
            cls = self._parse_js_class(node, content)
            if cls is not None:
                classes.append(cls)

        for child in node.children:
            self._walk_js_classes(child, content, classes)

    def _parse_js_class(
        self, node: tree_sitter.Node, content: bytes
    ) -> ClassInfo | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

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

        body = node.child_by_field_name("body")
        has_init = False
        has_super_call = False
        methods: list[MethodInfo] = []

        if body:
            for child in body.children:
                if child.type == "method_definition":
                    m = self._parse_js_method(child, content)
                    if m.name == "constructor":
                        has_init = True
                        has_super_call = self._contains_super_call(child)
                    methods.append(m)

        return ClassInfo(
            name=name or "<anonymous>",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent_names=tuple(parent_names),
            depth=1,
            has_init=has_init,
            has_super_call=has_super_call,
            methods=tuple(methods),
        )

    def _parse_js_method(
        self, node: tree_sitter.Node, content: bytes
    ) -> MethodInfo:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        body = node.child_by_field_name("body")
        body_text = ""
        calls_super_only = False

        if body:
            body_text = content[body.start_byte:body.end_byte].decode(
                "utf-8", errors="replace"
            )
            calls_super_only = self._is_super_only_body(body, content)

        return MethodInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            body_text=body_text,
            calls_super_only=calls_super_only,
        )

    # ── Java ──────────────────────────────────────────────────────────────

    def _extract_java_classes(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[ClassInfo]:
        classes: list[ClassInfo] = []
        self._walk_java_classes(root, content, classes)
        return classes

    def _walk_java_classes(
        self,
        node: tree_sitter.Node,
        content: bytes,
        classes: list[ClassInfo],
    ) -> None:
        if node.type in (
            "class_declaration", "interface_declaration",
            "enum_declaration", "record_declaration",
        ):
            cls = self._parse_java_class(node, content)
            if cls is not None:
                classes.append(cls)

        for child in node.children:
            self._walk_java_classes(child, content, classes)

    def _parse_java_class(
        self, node: tree_sitter.Node, content: bytes
    ) -> ClassInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        parent_names: list[str] = []
        extends_node = node.child_by_field_name("superclass")
        if not extends_node:
            extends_node = node.child_by_field_name("extends")
        if extends_node:
            for child in extends_node.children:
                if child.type == "type_identifier":
                    parent_names.append(
                        content[child.start_byte:child.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )

        implements_node = node.child_by_field_name("implements")
        if implements_node:
            for child in implements_node.children:
                if child.type == "type_identifier":
                    parent_names.append(
                        content[child.start_byte:child.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                    )

        body = node.child_by_field_name("body")
        has_init = False
        has_super_call = False
        methods: list[MethodInfo] = []

        if body:
            for child in body.children:
                if child.type == "constructor_declaration":
                    has_init = True
                    has_super_call = self._contains_java_super(child)
                elif child.type == "method_declaration":
                    m = self._parse_java_method(child, content)
                    methods.append(m)

        return ClassInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent_names=tuple(parent_names),
            depth=1,
            has_init=has_init,
            has_super_call=has_super_call,
            methods=tuple(methods),
        )

    def _contains_java_super(self, node: tree_sitter.Node) -> bool:
        for child in node.children:
            if child.type == "explicit_constructor_invocation":
                return True
            if child.type == "constructor_body":
                for sub in child.children:
                    if sub.type == "explicit_constructor_invocation":
                        return True
        return False

    def _parse_java_method(
        self, node: tree_sitter.Node, content: bytes
    ) -> MethodInfo:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        body = node.child_by_field_name("body")
        body_text = ""
        calls_super_only = False

        if body:
            body_text = content[body.start_byte:body.end_byte].decode(
                "utf-8", errors="replace"
            )
            calls_super_only = self._is_super_only_body(body, content)

        return MethodInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            body_text=body_text,
            calls_super_only=calls_super_only,
        )

    # ── Go ────────────────────────────────────────────────────────────────

    def _extract_go_structs(
        self, root: tree_sitter.Node, content: bytes
    ) -> list[ClassInfo]:
        classes: list[ClassInfo] = []
        self._walk_go_structs(root, content, classes)
        return classes

    def _walk_go_structs(
        self,
        node: tree_sitter.Node,
        content: bytes,
        classes: list[ClassInfo],
    ) -> None:
        if node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    cls = self._parse_go_type_spec(child, content)
                    if cls is not None:
                        classes.append(cls)

        for child in node.children:
            self._walk_go_structs(child, content, classes)

    def _parse_go_type_spec(
        self, node: tree_sitter.Node, content: bytes
    ) -> ClassInfo | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

        type_node = node.child_by_field_name("type")
        parent_names: list[str] = []

        if type_node and type_node.type == "struct_type":
            for child in type_node.children:
                if child.type == "field_declaration_list":
                    for field in child.children:
                        for fc in field.children:
                            if fc.type == "type_identifier":
                                parent_names.append(
                                    content[fc.start_byte:fc.end_byte].decode(
                                        "utf-8", errors="replace"
                                    )
                                )

        return ClassInfo(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent_names=tuple(parent_names),
            depth=1,
            has_init=False,
            has_super_call=False,
            methods=(),
        )
