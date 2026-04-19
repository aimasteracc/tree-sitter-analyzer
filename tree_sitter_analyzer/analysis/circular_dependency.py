"""Circular Dependency Detector.

Detects circular import/require dependencies in codebases by building
an import graph and finding cycles via DFS.

Supports Python, JavaScript/TypeScript, Java.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = setup_logger(__name__)


@dataclass(frozen=True)
class ImportEdge:
    source_file: str
    target_module: str
    line_number: int
    import_type: str


@dataclass(frozen=True)
class DependencyCycle:
    path: tuple[str, ...]
    length: int
    severity: str


@dataclass
class CircularDependencyResult:
    root_path: str
    total_cycles: int = 0
    cycles: list[DependencyCycle] = field(default_factory=list)
    edges: list[ImportEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "total_cycles": self.total_cycles,
            "cycles": [
                {
                    "path": list(c.path),
                    "length": c.length,
                    "severity": c.severity,
                }
                for c in self.cycles
            ],
            "edges": [
                {
                    "source_file": e.source_file,
                    "target_module": e.target_module,
                    "line_number": e.line_number,
                    "import_type": e.import_type,
                }
                for e in self.edges
            ],
        }


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(node: tree_sitter.Node) -> int:
    return node.start_point[0] + 1


def _walk(node: tree_sitter.Node) -> Any:
    yield node
    for child in node.children:
        yield from _walk(child)


def _find_cycles(
    graph: dict[str, set[str]],
) -> list[DependencyCycle]:
    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycles: list[DependencyCycle] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                idx = path.index(neighbor)
                cycle_path = tuple(path[idx:])
                severity = "high" if len(cycle_path) <= 2 else "medium"
                cycles.append(DependencyCycle(
                    path=cycle_path,
                    length=len(cycle_path),
                    severity=severity,
                ))

        path.pop()
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


class CircularDependencyAnalyzer(BaseAnalyzer):
    SUPPORTED_EXTENSIONS: set[str] = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}

    def analyze_file(self, file_path: str | Path) -> CircularDependencyResult:
        path = Path(file_path)
        ext = path.suffix
        result = CircularDependencyResult(root_path=str(path))

        if ext not in self.SUPPORTED_EXTENSIONS:
            return result

        edges = self.extract_imports(path)
        result.edges = edges
        return result

    def analyze_project(
        self,
        root: str | Path,
        exclude_patterns: list[str] | None = None,
    ) -> CircularDependencyResult:
        root = Path(root)
        result = CircularDependencyResult(root_path=str(root))
        exclude = set(exclude_patterns or []) | {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        }

        all_edges: list[ImportEdge] = []
        file_stems: dict[str, str] = {}

        for path in sorted(root.rglob("*")):
            if any(part in exclude for part in path.parts):
                continue
            if path.suffix in self.SUPPORTED_EXTENSIONS and path.is_file():
                stem = path.stem
                rel = str(path.relative_to(root))
                file_stems[stem] = rel
                edges = self.extract_imports(path)
                all_edges.extend(edges)

        result.edges = all_edges

        graph: dict[str, set[str]] = defaultdict(set)
        for edge in all_edges:
            target = edge.target_module.lstrip(".")
            source_stem = Path(edge.source_file).stem
            if target in file_stems and source_stem in file_stems:
                graph[source_stem].add(target)

        cycles = _find_cycles(graph)
        result.cycles = cycles
        result.total_cycles = len(cycles)

        return result

    def extract_imports(self, file_path: str | Path) -> list[ImportEdge]:
        path = Path(file_path)
        ext = path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            return []

        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        try:
            source = path.read_bytes()
        except OSError:
            return []

        tree = parser.parse(source)
        edges: list[ImportEdge] = []

        if ext == ".py":
            edges = self._extract_python_imports(tree, source, str(path))
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            edges = self._extract_js_imports(tree, source, str(path))
        elif ext == ".java":
            edges = self._extract_java_imports(tree, source, str(path))

        return edges

    def _extract_python_imports(
        self, tree: Tree, source: bytes, file_path: str,
    ) -> list[ImportEdge]:
        edges: list[ImportEdge] = []
        for node in _walk(tree.root_node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        mod = _node_text(child, source)
                        edges.append(ImportEdge(
                            source_file=file_path,
                            target_module=mod.split(".")[0],
                            line_number=_line(node),
                            import_type="import",
                        ))
            elif node.type == "import_from_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        mod = _node_text(child, source)
                        edges.append(ImportEdge(
                            source_file=file_path,
                            target_module=mod.split(".")[0],
                            line_number=_line(node),
                            import_type="from_import",
                        ))
        return edges

    def _extract_js_imports(
        self, tree: Tree, source: bytes, file_path: str,
    ) -> list[ImportEdge]:
        edges: list[ImportEdge] = []
        for node in _walk(tree.root_node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "string":
                        mod = _node_text(child, source).strip("'\"")
                        clean = mod.lstrip("./")
                        if clean:
                            edges.append(ImportEdge(
                                source_file=file_path,
                                target_module=clean,
                                line_number=_line(node),
                                import_type="import",
                            ))
            elif node.type == "call_expression":
                text = _node_text(node, source)
                if "require(" in text:
                    for child in node.children:
                        if child.type == "arguments":
                            for arg in child.children:
                                if arg.type == "string":
                                    mod = _node_text(arg, source).strip("'\"")
                                    clean = mod.lstrip("./")
                                    if clean:
                                        edges.append(ImportEdge(
                                            source_file=file_path,
                                            target_module=clean,
                                            line_number=_line(node),
                                            import_type="require",
                                        ))
        return edges

    def _extract_java_imports(
        self, tree: Tree, source: bytes, file_path: str,
    ) -> list[ImportEdge]:
        edges: list[ImportEdge] = []
        for node in _walk(tree.root_node):
            if node.type == "import_declaration":
                text = _node_text(node, source)
                if "import " in text:
                    mod = text.replace("import ", "").replace(";", "").strip()
                    parts = mod.split(".")
                    if len(parts) >= 2:
                        edges.append(ImportEdge(
                            source_file=file_path,
                            target_module=parts[-2],
                            line_number=_line(node),
                            import_type="import",
                        ))
        return edges
