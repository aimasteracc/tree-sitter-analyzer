"""Loop Complexity Analyzer.

Detects nested loops and estimates algorithmic complexity (O(n), O(n²), O(n³)).
Unlike cognitive complexity (reading difficulty) or nesting depth (control flow),
this focuses on performance implications of loop nesting.
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

_SUPERSCRIPT = {
    1: "\u00b9",
    2: "\u00b2",
    3: "\u00b3",
    4: "\u2074",
}


def _estimate_complexity(depth: int) -> str:
    if depth == 0:
        return "O(1)"
    if depth == 1:
        return "O(n)"
    sup = _SUPERSCRIPT.get(depth)
    if sup:
        return f"O(n{sup})"
    return f"O(n^{depth})"


@dataclass(frozen=True)
class LoopHotspot:
    """A loop nesting hotspot."""

    line_number: int
    depth: int
    complexity: str
    loop_type: str


@dataclass(frozen=True)
class LoopComplexityResult:
    """Aggregated loop complexity result for a file."""

    max_loop_depth: int
    estimated_complexity: str
    hotspots: tuple[LoopHotspot, ...]
    total_loops: int
    file_path: str


class LoopComplexityAnalyzer:
    """Analyzes loop nesting and estimates algorithmic complexity."""

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

    def analyze_file(self, file_path: Path | str) -> LoopComplexityResult:
        path = Path(file_path)
        if not path.exists():
            return LoopComplexityResult(
                max_loop_depth=0,
                estimated_complexity="O(1)",
                hotspots=(),
                total_loops=0,
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return LoopComplexityResult(
                max_loop_depth=0,
                estimated_complexity="O(1)",
                hotspots=(),
                total_loops=0,
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> LoopComplexityResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return LoopComplexityResult(
                max_loop_depth=0,
                estimated_complexity="O(1)",
                hotspots=(),
                total_loops=0,
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            loop_nodes = _PYTHON_LOOP_TYPES
        elif ext in {".js", ".ts", ".tsx", ".jsx"}:
            loop_nodes = _JS_LOOP_TYPES
        elif ext == ".java":
            loop_nodes = _JAVA_LOOP_TYPES
        elif ext == ".go":
            loop_nodes = _GO_LOOP_TYPES
        else:
            loop_nodes = frozenset()

        max_depth, total, hotspots = self._walk(tree.root_node, loop_nodes)

        return LoopComplexityResult(
            max_loop_depth=max_depth,
            estimated_complexity=_estimate_complexity(max_depth),
            hotspots=tuple(hotspots),
            total_loops=total,
            file_path=str(path),
        )

    def _walk(
        self, node: tree_sitter.Node, loop_types: frozenset[str]
    ) -> tuple[int, int, list[LoopHotspot]]:
        max_depth = 0
        total_loops = 0
        hotspots: list[LoopHotspot] = []

        def _add_hotspot(line: int, depth: int, ltype: str) -> None:
            nonlocal max_depth
            if depth > max_depth:
                max_depth = depth
            hotspots.append(
                LoopHotspot(
                    line_number=line,
                    depth=depth,
                    complexity=_estimate_complexity(depth),
                    loop_type=ltype,
                )
            )

        def visit(n: tree_sitter.Node, depth: int) -> None:
            nonlocal max_depth, total_loops

            if n.type in _PYTHON_COMPREHENSION_TYPES:
                for_in_clauses = [
                    c for c in n.children if c.type == "for_in_clause"
                ]
                for i, clause in enumerate(for_in_clauses):
                    d = depth + 1 + i
                    total_loops += 1
                    _add_hotspot(clause.start_point[0] + 1, d, "for_in_clause")
                for child in n.children:
                    if child.type != "for_in_clause":
                        visit(child, depth + len(for_in_clauses))
                return

            is_loop = n.type in loop_types
            new_depth = depth + 1 if is_loop else depth

            if is_loop:
                total_loops += 1
                _add_hotspot(n.start_point[0] + 1, new_depth, n.type)

            for child in n.children:
                visit(child, new_depth)

        visit(node, 0)
        return max_depth, total_loops, hotspots


# ── Language-specific loop node types ───────────────────────────────────

_PYTHON_LOOP_TYPES: frozenset[str] = frozenset({
    "for_statement",
    "while_statement",
    "for_in_clause",
})

_PYTHON_COMPREHENSION_TYPES: frozenset[str] = frozenset({
    "list_comprehension",
    "set_comprehension",
    "dictionary_comprehension",
    "generator_expression",
})

_JS_LOOP_TYPES: frozenset[str] = frozenset({
    "for_statement",
    "for_in_statement",
    "for_of_statement",
    "while_statement",
    "do_statement",
})

_JAVA_LOOP_TYPES: frozenset[str] = frozenset({
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
})

_GO_LOOP_TYPES: frozenset[str] = frozenset({
    "for_statement",
})
