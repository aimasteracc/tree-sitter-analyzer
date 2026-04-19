"""
Nesting Depth Analyzer.

Measures how deeply nested code structures are within functions.
Unlike cognitive complexity (SonarSource scoring) or cyclomatic complexity
(path counting), nesting depth simply counts the maximum level of control
flow nesting, making it immediately actionable: "flatten this pyramid."
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

RATING_GOOD = "good"
RATING_WARNING = "warning"
RATING_CRITICAL = "critical"

def _rating(max_depth: int) -> str:
    if max_depth <= 3:
        return RATING_GOOD
    if max_depth == 4:
        return RATING_WARNING
    return RATING_CRITICAL

@dataclass(frozen=True)
class DepthHotspot:
    """A location contributing to deep nesting."""

    line_number: int
    depth: int
    node_type: str

@dataclass(frozen=True)
class FunctionNesting:
    """Nesting depth analysis of a single function/method."""

    name: str
    start_line: int
    end_line: int
    max_depth: int
    avg_depth: float
    hotspots: tuple[DepthHotspot, ...]
    rating: str
    element_type: str

@dataclass(frozen=True)
class NestingDepthResult:
    """Aggregated nesting depth result for a file."""

    functions: tuple[FunctionNesting, ...]
    total_functions: int
    max_depth: int
    avg_depth: float
    deep_functions: int
    file_path: str

    def get_deep_functions(self, threshold: int = 4) -> list[FunctionNesting]:
        return [f for f in self.functions if f.max_depth >= threshold]

# Supplements for extensions where knowledge is not yet available
_NESTING_SUPPLEMENT: dict[str, frozenset[str]] = {
    ".ts": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "do_statement", "switch_statement",
        "try_statement", "with_statement",
    }),
    ".tsx": frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "do_statement", "switch_statement",
        "try_statement", "with_statement",
    }),
}


class NestingDepthAnalyzer(BaseAnalyzer):
    """Analyzes nesting depth of functions in source code."""

    def _get_nesting_nodes(self, ext: str) -> frozenset[str]:
        """Get nesting node types for the given extension via knowledge."""
        knowledge = self._get_knowledge(ext)
        nodes = knowledge.nesting_nodes
        if not nodes:
            nodes = _NESTING_SUPPLEMENT.get(ext, frozenset())
        return nodes

    def analyze_file(self, file_path: Path | str) -> NestingDepthResult:
        path = Path(file_path)
        if not path.exists():
            return NestingDepthResult(
                functions=(),
                total_functions=0,
                max_depth=0,
                avg_depth=0.0,
                deep_functions=0,
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return NestingDepthResult(
                functions=(),
                total_functions=0,
                max_depth=0,
                avg_depth=0.0,
                deep_functions=0,
                file_path=str(path),
            )

        functions = self._extract_functions(path, ext)
        total = len(functions)
        max_d = max((f.max_depth for f in functions), default=0)
        avg_d = (sum(f.max_depth for f in functions) / total) if total > 0 else 0.0
        deep = sum(1 for f in functions if f.max_depth >= 4)

        return NestingDepthResult(
            functions=tuple(functions),
            total_functions=total,
            max_depth=max_d,
            avg_depth=round(avg_d, 2),
            deep_functions=deep,
            file_path=str(path),
        )

    def _extract_functions(self, path: Path, ext: str) -> list[FunctionNesting]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)
        nesting = self._get_nesting_nodes(ext)

        if ext == ".py":
            return self._extract_python(tree.root_node, content, nesting)
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content, nesting)
        if ext == ".java":
            return self._extract_java(tree.root_node, content, nesting)
        if ext == ".go":
            return self._extract_go(tree.root_node, content, nesting)
        return []

    # ── Depth measurement helper ──────────────────────────────────────────

    def _measure_depth(
        self,
        node: tree_sitter.Node,
        nesting_nodes: set[str] | frozenset[str],
    ) -> tuple[int, list[DepthHotspot]]:
        """Walk AST and measure max nesting depth. Returns (max_depth, hotspots)."""
        max_depth = 0
        hotspots: list[DepthHotspot] = []

        def walk(n: tree_sitter.Node, depth: int) -> None:
            nonlocal max_depth
            if n.type in nesting_nodes:
                new_depth = depth + 1
                if new_depth > max_depth:
                    max_depth = new_depth
                hotspots.append(
                    DepthHotspot(
                        line_number=n.start_point[0] + 1,
                        depth=new_depth,
                        node_type=n.type,
                    )
                )
                for child in n.children:
                    walk(child, new_depth)
            else:
                for child in n.children:
                    walk(child, depth)

        walk(node, 0)
        return max_depth, hotspots

    # ── Python ────────────────────────────────────────────────────────────

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes, nesting: frozenset[str]
    ) -> list[FunctionNesting]:
        results: list[FunctionNesting] = []
        self._walk_python(root, content, results, in_class=False, nesting=nesting)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionNesting],
        in_class: bool,
        nesting: frozenset[str],
    ) -> None:
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    self._walk_python(child, content, results, in_class, nesting)
            return

        if node.type == "class_definition":
            for child in node.children:
                self._walk_python(child, content, results, in_class=True, nesting=nesting)
            return

        if node.type == "function_definition":
            fn = self._analyze_python_function(node, content, in_class, nesting)
            if fn is not None:
                results.append(fn)

        for child in node.children:
            self._walk_python(child, content, results, in_class, nesting)

    def _analyze_python_function(
        self, node: tree_sitter.Node, content: bytes, in_class: bool, nesting: frozenset[str]
    ) -> FunctionNesting | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode(
            "utf-8", errors="replace"
        )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            return FunctionNesting(
                name=name,
                start_line=start_line,
                end_line=end_line,
                max_depth=0,
                avg_depth=0.0,
                hotspots=(),
                rating=_rating(0),
                element_type="method" if in_class else "function",
            )

        max_d, hotspots = self._measure_depth(body, nesting)
        avg_d = (sum(h.depth for h in hotspots) / len(hotspots)) if hotspots else 0.0

        return FunctionNesting(
            name=name,
            start_line=start_line,
            end_line=end_line,
            max_depth=max_d,
            avg_depth=round(avg_d, 2),
            hotspots=tuple(hotspots),
            rating=_rating(max_d),
            element_type="method" if in_class else "function",
        )

    # ── JavaScript / TypeScript ───────────────────────────────────────────

    def _extract_js(
        self, root: tree_sitter.Node, content: bytes, nesting: frozenset[str]
    ) -> list[FunctionNesting]:
        results: list[FunctionNesting] = []
        self._walk_js(root, content, results, in_class=False, nesting=nesting)
        return results

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionNesting],
        in_class: bool,
        nesting: frozenset[str],
    ) -> None:
        if node.type in {"class_declaration", "class_expression"}:
            for child in node.children:
                self._walk_js(child, content, results, in_class=True, nesting=nesting)
            return

        if node.type in {"function_declaration", "generator_function_declaration"}:
            fn = self._analyze_js_function(node, content, in_class, "function", nesting)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_definition":
            fn = self._analyze_js_function(node, content, True, "method", nesting)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "arrow_function":
            fn = self._analyze_js_function(node, content, in_class, "arrow_function", nesting)
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_js(child, content, results, in_class, nesting)

    def _analyze_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        element_type: str,
        nesting: frozenset[str],
    ) -> FunctionNesting | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        max_d, hotspots = self._measure_depth(body, nesting)
        avg_d = (sum(h.depth for h in hotspots) / len(hotspots)) if hotspots else 0.0

        return FunctionNesting(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            max_depth=max_d,
            avg_depth=round(avg_d, 2),
            hotspots=tuple(hotspots),
            rating=_rating(max_d),
            element_type="method" if in_class else element_type,
        )

    # ── Java ──────────────────────────────────────────────────────────────

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes, nesting: frozenset[str]
    ) -> list[FunctionNesting]:
        results: list[FunctionNesting] = []
        self._walk_java(root, content, results, in_class=False, nesting=nesting)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionNesting],
        in_class: bool,
        nesting: frozenset[str],
    ) -> None:
        if node.type in {"class_declaration", "interface_declaration",
                          "enum_declaration", "record_declaration"}:
            for child in node.children:
                self._walk_java(child, content, results, in_class=True, nesting=nesting)
            return

        if node.type == "method_declaration":
            fn = self._analyze_java_method(node, content, in_class, nesting=nesting)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "constructor_declaration":
            fn = self._analyze_java_method(node, content, True, "<init>", nesting=nesting)
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_java(child, content, results, in_class, nesting)

    def _analyze_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        in_class: bool,
        override_name: str | None = None,
        nesting: frozenset[str] = frozenset(),
    ) -> FunctionNesting | None:
        if override_name:
            name = override_name
        else:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        body = node.child_by_field_name("body")
        if not body:
            body = node

        max_d, hotspots = self._measure_depth(body, nesting)
        avg_d = (sum(h.depth for h in hotspots) / len(hotspots)) if hotspots else 0.0

        return FunctionNesting(
            name=name,
            start_line=start_line,
            end_line=end_line,
            max_depth=max_d,
            avg_depth=round(avg_d, 2),
            hotspots=tuple(hotspots),
            rating=_rating(max_d),
            element_type="method" if in_class else "function",
        )

    # ── Go ────────────────────────────────────────────────────────────────

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes, nesting: frozenset[str]
    ) -> list[FunctionNesting]:
        results: list[FunctionNesting] = []
        self._walk_go(root, content, results, nesting)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        results: list[FunctionNesting],
        nesting: frozenset[str],
    ) -> None:
        if node.type == "function_declaration":
            fn = self._analyze_go_func(node, content, "function", nesting)
            if fn is not None:
                results.append(fn)
            return

        if node.type == "method_declaration":
            fn = self._analyze_go_func(node, content, "method", nesting)
            if fn is not None:
                results.append(fn)
            return

        for child in node.children:
            self._walk_go(child, content, results, nesting)

    def _analyze_go_func(
        self,
        node: tree_sitter.Node,
        content: bytes,
        element_type: str,
        nesting: frozenset[str],
    ) -> FunctionNesting | None:
        name_node = node.child_by_field_name("name")
        name = ""
        if name_node:
            name = content[name_node.start_byte:name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        max_d, hotspots = self._measure_depth(node, nesting)
        avg_d = (sum(h.depth for h in hotspots) / len(hotspots)) if hotspots else 0.0

        return FunctionNesting(
            name=name or "<anonymous>",
            start_line=start_line,
            end_line=end_line,
            max_depth=max_d,
            avg_depth=round(avg_d, 2),
            hotspots=tuple(hotspots),
            rating=_rating(max_d),
            element_type=element_type,
        )
