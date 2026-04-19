"""God Class Detector.

Detects classes that are too large and have too many responsibilities.
These classes tend to attract functionality from other parts of the system
and become difficult to maintain.

Issues detected:
  - god_class: 10+ methods AND 8+ fields
  - large_class: 7-9 methods AND 5+ fields
  - low_cohesion: 7+ methods with any fields but below god_class threshold

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

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
SEVERITY_LOW = "low"

ISSUE_GOD_CLASS = "god_class"
ISSUE_LARGE_CLASS = "large_class"
ISSUE_LOW_COHESION = "low_cohesion"

GOD_CLASS_METHOD_THRESHOLD = 10
GOD_CLASS_FIELD_THRESHOLD = 8
LARGE_CLASS_METHOD_THRESHOLD = 7
LARGE_CLASS_FIELD_THRESHOLD = 5

_SEVERITY_MAP: dict[str, str] = {
    ISSUE_GOD_CLASS: SEVERITY_HIGH,
    ISSUE_LARGE_CLASS: SEVERITY_MEDIUM,
    ISSUE_LOW_COHESION: SEVERITY_LOW,
}

_DESCRIPTIONS: dict[str, str] = {
    ISSUE_GOD_CLASS: "Class has too many methods and fields, indicating too many responsibilities",
    ISSUE_LARGE_CLASS: "Class is approaching god class territory with many methods and fields",
    ISSUE_LOW_COHESION: "Methods access a small fraction of total fields, suggesting split opportunities",
}

_SUGGESTIONS: dict[str, str] = {
    ISSUE_GOD_CLASS: "Split this class into smaller, focused classes with single responsibilities",
    ISSUE_LARGE_CLASS: "Consider extracting related methods into a separate class",
    ISSUE_LOW_COHESION: "Group related methods by the fields they access and extract into separate classes",
}

_CLASS_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"class_definition"}),
    ".js": frozenset({"class_declaration"}),
    ".jsx": frozenset({"class_declaration"}),
    ".ts": frozenset({"class_declaration"}),
    ".tsx": frozenset({"class_declaration"}),
    ".java": frozenset({"class_declaration"}),
    ".go": frozenset({"type_declaration"}),
}

_METHOD_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"function_definition"}),
    ".js": frozenset({"method_definition"}),
    ".jsx": frozenset({"method_definition"}),
    ".ts": frozenset({"method_definition"}),
    ".tsx": frozenset({"method_definition"}),
    ".java": frozenset({"method_declaration", "constructor_declaration"}),
    ".go": frozenset({"method_declaration"}),
}

_FIELD_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"expression_statement"}),
    ".js": frozenset({"public_field_definition", "field_definition"}),
    ".jsx": frozenset({"public_field_definition", "field_definition"}),
    ".ts": frozenset({"public_field_definition", "field_definition"}),
    ".tsx": frozenset({"public_field_definition", "field_definition"}),
    ".java": frozenset({"field_declaration"}),
    ".go": frozenset({"field_declaration"}),
}


@dataclass(frozen=True)
class GodClassIssue:
    """A single god class issue."""

    class_name: str
    line_number: int
    issue_type: str
    method_count: int
    field_count: int
    severity: str

    @property
    def description(self) -> str:
        return _DESCRIPTIONS.get(self.issue_type, "")

    @property
    def suggestion(self) -> str:
        return _SUGGESTIONS.get(self.issue_type, "")

    def to_dict(self) -> dict[str, object]:
        return {
            "class_name": self.class_name,
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "method_count": self.method_count,
            "field_count": self.field_count,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class ClassStats:
    """Statistics for a single class."""

    class_name: str
    line_number: int
    method_count: int
    field_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "class_name": self.class_name,
            "line_number": self.line_number,
            "method_count": self.method_count,
            "field_count": self.field_count,
        }


@dataclass(frozen=True)
class GodClassResult:
    """Aggregated god class analysis result."""

    total_classes: int
    issues: tuple[GodClassIssue, ...]
    class_stats: tuple[ClassStats, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_classes": self.total_classes,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "class_stats": [s.to_dict() for s in self.class_stats],
            "file_path": self.file_path,
        }


def _classify_issue(
    method_count: int, field_count: int
) -> str | None:
    if method_count >= GOD_CLASS_METHOD_THRESHOLD and field_count >= GOD_CLASS_FIELD_THRESHOLD:
        return ISSUE_GOD_CLASS
    if method_count >= LARGE_CLASS_METHOD_THRESHOLD and field_count >= LARGE_CLASS_FIELD_THRESHOLD:
        return ISSUE_LARGE_CLASS
    return None


class GodClassAnalyzer:
    """Analyzes classes for excessive size and responsibility."""

    def __init__(self) -> None:
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

    def analyze_file(self, file_path: Path | str) -> GodClassResult:
        path = Path(file_path)
        if not path.exists():
            return GodClassResult(
                total_classes=0,
                issues=(),
                class_stats=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return GodClassResult(
                total_classes=0,
                issues=(),
                class_stats=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> GodClassResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return GodClassResult(
                total_classes=0,
                issues=(),
                class_stats=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        class_types = _CLASS_TYPES.get(ext, frozenset())
        method_types = _METHOD_TYPES.get(ext, frozenset())
        field_types = _FIELD_TYPES.get(ext, frozenset())

        issues: list[GodClassIssue] = []
        stats: list[ClassStats] = []
        total = 0

        # Pre-build Go receiver method map (single pass, O(n))
        go_method_counts: dict[str, int] = {}
        if ext == ".go":
            go_method_counts = self._build_go_method_map(tree.root_node, content)

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total

            if node.type in class_types:
                total += 1
                name = self._get_class_name(node, content)
                if ext == ".go" and name == "<anonymous>":
                    name = self._get_go_type_name(node, content)
                body = self._get_class_body(node)
                target = body if body is not None else node

                method_count = self._count_direct(target, method_types)
                if ext == ".py":
                    field_count = self._count_python_fields(target, content)
                elif ext == ".go":
                    field_count = self._count_go_fields(node)
                    method_count = go_method_counts.get(name, 0)
                else:
                    field_count = self._count_direct(target, field_types)

                stats.append(ClassStats(
                    class_name=name,
                    line_number=node.start_point[0] + 1,
                    method_count=method_count,
                    field_count=field_count,
                ))

                issue_type = _classify_issue(method_count, field_count)
                if issue_type is not None:
                    severity = _SEVERITY_MAP[issue_type]
                    issues.append(GodClassIssue(
                        class_name=name,
                        line_number=node.start_point[0] + 1,
                        issue_type=issue_type,
                        method_count=method_count,
                        field_count=field_count,
                        severity=severity,
                    ))
                elif (
                    method_count >= LARGE_CLASS_METHOD_THRESHOLD
                    and field_count > 0
                ):
                    issues.append(GodClassIssue(
                        class_name=name,
                        line_number=node.start_point[0] + 1,
                        issue_type=ISSUE_LOW_COHESION,
                        method_count=method_count,
                        field_count=field_count,
                        severity=SEVERITY_LOW,
                    ))

                if body is not None:
                    for child in body.children:
                        if child.type in class_types:
                            visit(child)
                return

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return GodClassResult(
            total_classes=total,
            issues=tuple(issues),
            class_stats=tuple(stats),
            file_path=str(path),
        )

    def _count_python_fields(
        self, body: tree_sitter.Node, content: bytes
    ) -> int:
        """Count unique self.x attributes assigned in Python methods."""
        fields: set[str] = set()
        for child in body.children:
            if child.type == "function_definition":
                self._collect_self_attrs(child, content, fields)
        return len(fields)

    def _collect_self_attrs(
        self, node: tree_sitter.Node, content: bytes, attrs: set[str]
    ) -> None:
        """Recursively find self.xxx = ... assignments."""
        if node.type == "assignment":
            left = node.child_by_field_name("left")
            if left is not None and left.type == "attribute":
                obj = left.child_by_field_name("object")
                attr = left.child_by_field_name("attribute")
                if (
                    obj is not None
                    and attr is not None
                    and content[obj.start_byte:obj.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    == "self"
                ):
                    name = content[attr.start_byte:attr.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    attrs.add(name)
        for child in node.children:
            self._collect_self_attrs(child, content, attrs)

    def _count_go_fields(self, node: tree_sitter.Node) -> int:
        """Count fields in a Go struct by drilling into field_declaration_list."""
        for child in node.children:
            if child.type == "type_spec":
                for sub in child.children:
                    if sub.type == "struct_type":
                        for inner in sub.children:
                            if inner.type == "field_declaration_list":
                                return sum(
                                    1
                                    for c in inner.children
                                    if c.type == "field_declaration"
                                )
        return 0

    def _build_go_method_map(
        self, root: tree_sitter.Node, content: bytes
    ) -> dict[str, int]:
        """Single-pass build of type_name -> method_count for all Go receivers."""
        counts: dict[str, int] = {}
        for node in self._walk_all(root):
            if node.type == "method_declaration":
                receiver = node.child_by_field_name("receiver")
                if receiver is not None:
                    text = content[
                        receiver.start_byte:receiver.end_byte
                    ].decode("utf-8", errors="replace")
                    # Extract type name from receiver: (r *TypeName) or (r TypeName)
                    for token in text.replace("*", " ").replace("(", " ").replace(")", " ").split():
                        if token and not token.isascii() or token[0].isupper():
                            if token not in ("r", "s", "self", "this"):
                                counts[token] = counts.get(token, 0) + 1
                                break
        return counts

    @staticmethod
    def _walk_all(node: tree_sitter.Node) -> list[tree_sitter.Node]:
        """Flat list of all descendants (BFS via deque for O(n))."""
        result: list[tree_sitter.Node] = []
        queue: deque[tree_sitter.Node] = deque(node.children)
        while queue:
            current = queue.popleft()
            result.append(current)
            queue.extend(current.children)
        return result

    @staticmethod
    def _get_go_type_name(
        node: tree_sitter.Node, content: bytes
    ) -> str:
        """Extract type name from Go type_declaration -> type_spec -> name."""
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    return content[
                        name_node.start_byte:name_node.end_byte
                    ].decode("utf-8", errors="replace")
        return "<anonymous>"

    @staticmethod
    def _get_class_body(
        node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        body = node.child_by_field_name("body")
        if body is not None:
            return body
        for child in node.children:
            if child.type in ("block", "class_body", "declaration_list"):
                return child
        return None

    @staticmethod
    def _get_class_name(
        node: tree_sitter.Node, content: bytes
    ) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return content[
                name_node.start_byte:name_node.end_byte
            ].decode("utf-8", errors="replace")
        return "<anonymous>"

    @staticmethod
    def _count_direct(
        node: tree_sitter.Node, types: frozenset[str]
    ) -> int:
        count = 0
        for child in node.children:
            if child.type in types:
                count += 1
        return count
