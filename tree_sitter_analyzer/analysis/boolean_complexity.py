"""Boolean Complexity Analyzer.

Detects overly complex boolean expressions that are hard to reason about.
Counts conditions in boolean chains (&&/||/and/or) and flags expressions
with too many conditions, suggesting extraction into named variables.
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

RATING_GOOD = "good"
RATING_WARNING = "warning"
RATING_CRITICAL = "critical"


def _rating(condition_count: int) -> str:
    if condition_count <= 3:
        return RATING_GOOD
    if condition_count == 4:
        return RATING_WARNING
    return RATING_CRITICAL


# Boolean operator node types per language
_PYTHON_BOOL_OPS: frozenset[str] = frozenset({
    "boolean_operator",
})

_CSTYLE_BOOL_EXPR: frozenset[str] = frozenset({
    "binary_expression",
})

_CSTYLE_BOOL_OPS: frozenset[str] = frozenset({
    "&&",
    "||",
})


def _is_cstyle_bool(node: tree_sitter.Node) -> bool:
    """Check if a binary_expression uses a boolean operator."""
    if node.type != "binary_expression":
        return False
    return any(c.type in _CSTYLE_BOOL_OPS for c in node.children)


def _get_bool_ops(ext: str) -> frozenset[str]:
    if ext == ".py":
        return _PYTHON_BOOL_OPS
    return _CSTYLE_BOOL_EXPR


@dataclass(frozen=True)
class BooleanHotspot:
    """A complex boolean expression."""

    line_number: int
    condition_count: int
    expression: str


@dataclass(frozen=True)
class BooleanComplexityResult:
    """Aggregated boolean complexity result for a file."""

    max_conditions: int
    total_expressions: int
    hotspots: tuple[BooleanHotspot, ...]
    file_path: str


class BooleanComplexityAnalyzer:
    """Analyzes boolean expression complexity in source code."""

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

    def analyze_file(self, file_path: Path | str) -> BooleanComplexityResult:
        path = Path(file_path)
        if not path.exists():
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> BooleanComplexityResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return BooleanComplexityResult(
                max_conditions=0,
                total_expressions=0,
                hotspots=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        total = 0
        max_cond = 0
        hotspots: list[BooleanHotspot] = []

        def _is_bool_node(node: tree_sitter.Node) -> bool:
            if ext == ".py":
                return node.type == "boolean_operator"
            return _is_cstyle_bool(node)

        def visit(node: tree_sitter.Node) -> None:
            nonlocal total, max_cond

            if _is_bool_node(node):
                count = self._count_conditions(node, ext)
                total += 1
                if count > max_cond:
                    max_cond = count
                if count >= 4:
                    text = content[
                        node.start_byte:node.end_byte
                    ].decode("utf-8", errors="replace")
                    if len(text) > 80:
                        text = text[:77] + "..."
                    hotspots.append(
                        BooleanHotspot(
                            line_number=node.start_point[0] + 1,
                            condition_count=count,
                            expression=text,
                        )
                    )

            for child in node.children:
                visit(child)

        visit(tree.root_node)

        return BooleanComplexityResult(
            max_conditions=max_cond,
            total_expressions=total,
            hotspots=tuple(hotspots),
            file_path=str(path),
        )

    def _count_conditions(
        self, node: tree_sitter.Node, ext: str
    ) -> int:
        """Count leaf conditions in a boolean expression tree."""
        is_bool = (
            node.type == "boolean_operator"
            if ext == ".py"
            else _is_cstyle_bool(node)
        )
        if not is_bool:
            return 1
        count = 0
        for child in node.children:
            if child.type in ("&&", "||", "and", "or"):
                continue
            count += self._count_conditions(child, ext)
        return count
