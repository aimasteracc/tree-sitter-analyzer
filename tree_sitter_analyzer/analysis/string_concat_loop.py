"""String Concatenation in Loops Analyzer.

Detects string concatenation (+=) inside loops, which causes O(n^2)
performance due to repeated string copying. Suggests using join(),
StringBuilder, or buffer instead.
"""
from __future__ import annotations

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

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"


def _severity(loop_depth: int) -> str:
    if loop_depth >= 2:
        return SEVERITY_HIGH
    if loop_depth == 1:
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


@dataclass(frozen=True)
class ConcatHotspot:
    """A string concatenation inside a loop."""

    line_number: int
    loop_type: str
    concat_operator: str
    severity: str
    variable: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "loop_type": self.loop_type,
            "concat_operator": self.concat_operator,
            "severity": self.severity,
            "variable": self.variable,
        }


@dataclass(frozen=True)
class StringConcatLoopResult:
    """Aggregated string concat in loop analysis result."""

    total_hotspots: int
    hotspots: tuple[ConcatHotspot, ...]
    file_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_hotspots": self.total_hotspots,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "file_path": self.file_path,
        }


_LOOP_TYPES: dict[str, frozenset[str]] = {
    ".py": frozenset({"for_statement", "while_statement"}),
    ".js": frozenset({
        "for_statement", "while_statement",
        "do_statement", "for_in_statement",
    }),
    ".jsx": frozenset({
        "for_statement", "while_statement",
        "do_statement", "for_in_statement",
    }),
    ".ts": frozenset({
        "for_statement", "while_statement",
        "do_statement", "for_in_statement",
    }),
    ".tsx": frozenset({
        "for_statement", "while_statement",
        "do_statement", "for_in_statement",
    }),
    ".java": frozenset({
        "for_statement", "while_statement",
        "do_statement", "enhanced_for_statement",
    }),
    ".go": frozenset({"for_statement"}),
}


class StringConcatLoopAnalyzer:
    """Analyzes string concatenation inside loops."""

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

    def analyze_file(self, file_path: Path | str) -> StringConcatLoopResult:
        path = Path(file_path)
        if not path.exists():
            return StringConcatLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return StringConcatLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> StringConcatLoopResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return StringConcatLoopResult(
                total_hotspots=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        hotspots: list[ConcatHotspot] = []
        loop_types = _LOOP_TYPES.get(ext, frozenset())

        def find_loops(
            node: tree_sitter.Node, depth: int
        ) -> list[tuple[tree_sitter.Node, int]]:
            result: list[tuple[tree_sitter.Node, int]] = []
            if node.type in loop_types:
                result.append((node, depth))
                for child in node.children:
                    result.extend(find_loops(child, depth + 1))
            else:
                for child in node.children:
                    result.extend(find_loops(child, depth))
            return result

        loops = find_loops(tree.root_node, 0)

        for loop_node, loop_depth in loops:
            self._find_concats(
                loop_node, content, ext, loop_depth, hotspots
            )

        return StringConcatLoopResult(
            total_hotspots=len(hotspots),
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _find_concats(
        self,
        loop_node: tree_sitter.Node,
        content: bytes,
        ext: str,
        loop_depth: int,
        hotspots: list[ConcatHotspot],
    ) -> None:
        loop_type_name = loop_node.type.replace("_statement", "")
        concat_finder = _get_concat_finder(ext)

        def visit(node: tree_sitter.Node) -> None:
            if node.type in _LOOP_TYPES.get(ext, frozenset()):
                return

            hit = concat_finder.find(node, content)
            if hit is not None:
                var_name, operator = hit
                hotspots.append(
                    ConcatHotspot(
                        line_number=node.start_point[0] + 1,
                        loop_type=loop_type_name,
                        concat_operator=operator,
                        severity=_severity(loop_depth + 1),
                        variable=var_name,
                    )
                )

            for child in node.children:
                visit(child)

        for child in loop_node.children:
            visit(child)


def _get_concat_finder(
    ext: str,
) -> type[_BaseConcatFinder]:
    if ext == ".py":
        return _PythonConcatFinder
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return _JSConcatFinder
    if ext == ".java":
        return _JavaConcatFinder
    if ext == ".go":
        return _GoConcatFinder
    return _BaseConcatFinder


class _BaseConcatFinder:
    @staticmethod
    def find(
        node: tree_sitter.Node, content: bytes
    ) -> tuple[str, str] | None:
        return None


class _PythonConcatFinder(_BaseConcatFinder):
    @staticmethod
    def find(
        node: tree_sitter.Node, content: bytes
    ) -> tuple[str, str] | None:
        if node.type == "augmented_assignment":
            op_node = node.child_by_field_name("operator")
            if (
                op_node is not None
                and content[op_node.start_byte:op_node.end_byte] == b"+="
            ):
                left = node.child_by_field_name("left")
                if left is not None:
                    var_name = content[
                        left.start_byte:left.end_byte
                    ].decode("utf-8", errors="replace")
                    return (var_name, "+=")
        return None


class _JSConcatFinder(_BaseConcatFinder):
    @staticmethod
    def find(
        node: tree_sitter.Node, content: bytes
    ) -> tuple[str, str] | None:
        if node.type in (
            "assignment_expression",
            "augmented_assignment_expression",
        ):
            op_node = node.child_by_field_name("operator")
            if op_node is not None:
                op_text = content[
                    op_node.start_byte:op_node.end_byte
                ].decode("utf-8", errors="replace")
                if op_text == "+=":
                    left = node.child_by_field_name("left")
                    if left is not None:
                        var_name = content[
                            left.start_byte:left.end_byte
                        ].decode("utf-8", errors="replace")
                        return (var_name, "+=")
        return None


class _JavaConcatFinder(_BaseConcatFinder):
    @staticmethod
    def find(
        node: tree_sitter.Node, content: bytes
    ) -> tuple[str, str] | None:
        if node.type == "assignment_expression":
            op_node = node.child_by_field_name("operator")
            if op_node is not None:
                op_text = content[
                    op_node.start_byte:op_node.end_byte
                ].decode("utf-8", errors="replace")
                if op_text == "+=":
                    left = node.child_by_field_name("left")
                    if left is not None:
                        var_name = content[
                            left.start_byte:left.end_byte
                        ].decode("utf-8", errors="replace")
                        return (var_name, "+=")
        return None


class _GoConcatFinder(_BaseConcatFinder):
    @staticmethod
    def find(
        node: tree_sitter.Node, content: bytes
    ) -> tuple[str, str] | None:
        if node.type == "assignment_statement":
            op_node = node.child_by_field_name("operator")
            if (
                op_node is not None
                and content[op_node.start_byte:op_node.end_byte] == b"+="
            ):
                left = node.child_by_field_name("left")
                if left is not None:
                    var_name = content[
                        left.start_byte:left.end_byte
                    ].decode("utf-8", errors="replace")
                    return (var_name, "+=")
        return None
