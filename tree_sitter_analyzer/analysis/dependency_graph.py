"""
Dependency graph builder for source code projects.

Builds a directed graph where nodes are source files and edges represent
import/usage relationships. Supports JSON, DOT (Graphviz), and Mermaid output.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class DependencyGraph:
    """Immutable directed graph of file dependencies."""

    nodes: dict[str, dict[str, str | int]]
    edges: list[tuple[str, str]]

    def to_json(self) -> str:
        """Export as JSON adjacency list."""
        adjacency: dict[str, list[str]] = {}
        for src, dst in self.edges:
            adjacency.setdefault(src, []).append(dst)
        data = {
            "nodes": dict(sorted(self.nodes.items())),
            "edges": adjacency,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_mermaid(self) -> str:
        """Export as Mermaid flowchart with cycle highlighting."""
        lines = ["graph LR"]
        seen_edges: set[tuple[str, str]] = set()

        # Detect cyclic edges for visual highlighting
        cycle_edges = self._cycle_edge_set()

        for src, dst in self.edges:
            edge = (src, dst)
            if edge not in seen_edges:
                seen_edges.add(edge)
                safe_src = _mermaid_id(src)
                safe_dst = _mermaid_id(dst)
                if edge in cycle_edges:
                    lines.append(f"    {safe_src} -.->|cycle| {safe_dst}")
                else:
                    lines.append(f"    {safe_src} --> {safe_dst}")
        if not seen_edges:
            for node_name in sorted(self.nodes):
                lines.append(f"    {_mermaid_id(node_name)}")
        return "\n".join(lines)

    def to_dot(self) -> str:
        """Export as DOT (Graphviz) with cycle highlighting."""
        cycle_edges = self._cycle_edge_set()
        lines = ["digraph dependencies {", '    rankdir=LR;']
        for src, dst in self.edges:
            style = ' [style=dashed, color=red, label="cycle"]' if (src, dst) in cycle_edges else ""
            lines.append(f'    "{src}" -> "{dst}"{style};')
        lines.append("}")
        return "\n".join(lines)

    def _cycle_edge_set(self) -> set[tuple[str, str]]:
        """Identify edges that participate in cycles."""
        sccs = self.find_cycles()
        if not sccs:
            return set()
        cycle_nodes: set[str] = set()
        for scc in sccs:
            cycle_nodes.update(scc)
        edge_set: set[tuple[str, str]] = set()
        for src, dst in self.edges:
            if src in cycle_nodes and dst in cycle_nodes:
                edge_set.add((src, dst))
        return edge_set

    def has_cycle(self) -> bool:
        """Check if the graph contains any cycle."""
        adjacency: dict[str, list[str]] = {}
        for src, dst in self.edges:
            adjacency.setdefault(src, []).append(dst)
        visited: set[str] = set()
        in_stack: set[str] = set()

        def _dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    if _dfs(neighbor):
                        return True
                elif neighbor in in_stack:
                    return True
            in_stack.discard(node)
            return False

        for node in self.nodes:
            if node not in visited:
                if _dfs(node):
                    return True
        return False

    def find_cycles(self) -> list[list[str]]:
        """Find all strongly connected components with size >= 2 using Tarjan's algorithm."""
        adjacency: dict[str, list[str]] = {}
        for src, dst in self.edges:
            adjacency.setdefault(src, []).append(dst)

        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        sccs: list[list[str]] = []

        def _strongconnect(node: str) -> None:
            indices[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in indices:
                    _strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) >= 2:
                    sccs.append(sorted(scc))

        # Detect self-loops as single-node cycles
        for src, dst in self.edges:
            if src == dst and src in self.nodes:
                if not any(src in scc for scc in sccs):
                    sccs.append([src])

        for node in sorted(self.nodes):
            if node not in indices:
                _strongconnect(node)

        return sccs

    def topological_sort(self) -> list[str] | None:
        """Return topological ordering, or None if graph has cycles."""
        if self.has_cycle():
            return None

        adjacency: dict[str, list[str]] = {}
        in_degree: dict[str, int] = dict.fromkeys(self.nodes, 0)
        for src, dst in self.edges:
            adjacency.setdefault(src, []).append(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

        queue: list[str] = sorted(n for n in self.nodes if in_degree.get(n, 0) == 0)
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()

        return result if len(result) == len(self.nodes) else None

    def compute_pagerank(self, *, damping: float = 0.85, iterations: int = 20) -> dict[str, float]:
        """Compute PageRank scores for all nodes."""
        if not self.nodes:
            return {}

        n = len(self.nodes)
        ranks: dict[str, float] = dict.fromkeys(self.nodes, 1.0 / n)

        out_degree: dict[str, int] = dict.fromkeys(self.nodes, 0)
        in_edges: dict[str, list[str]] = {name: [] for name in self.nodes}

        for src, dst in self.edges:
            out_degree[src] = out_degree.get(src, 0) + 1
            in_edges.setdefault(dst, []).append(src)

        for _ in range(iterations):
            new_ranks: dict[str, float] = {}
            for node in self.nodes:
                rank_sum = sum(
                    ranks.get(src, 0) / max(out_degree.get(src, 1), 1)
                    for src in in_edges.get(node, [])
                )
                new_ranks[node] = (1 - damping) / n + damping * rank_sum
            ranks = new_ranks

        return ranks


def _mermaid_id(name: str) -> str:
    """Convert a file name to a valid Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9]", "_", Path(name).stem)


@dataclass
class _NodeInfo:
    path: str
    language: str = "unknown"
    imports: list[str] = field(default_factory=list)


class DependencyGraphBuilder:
    """Build a dependency graph from source files in a project."""

    IMPORT_PATTERNS: dict[str, re.Pattern[str]] = {
        "java": re.compile(r"import\s+(?:static\s+)?([\w.]+)\s*;"),
        "python": re.compile(r"(?:from|import)\s+([\w.]+)"),
        "javascript": re.compile(r"(?:import|require)\s*\(?\s*[\"']([./\w-]+)[\"']"),
        "typescript": re.compile(r"(?:import|require)\s*\(?\s*[\"']([./\w-]+)[\"']"),
        "go": re.compile(r"import\s+[\"\`]([\w./-]+)[\"\`]"),
        "rust": re.compile(r"use\s+([\w:]+)"),
        "csharp": re.compile(r"using\s+([\w.]+)\s*;"),
        "kotlin": re.compile(r"import\s+([\w.]+)"),
    }

    EXTENSION_TO_LANG: dict[str, str] = {
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".cs": "csharp",
        ".kt": "kotlin",
    }

    def __init__(self, project_root: str) -> None:
        self.project_root = Path(project_root)

    def build(self) -> DependencyGraph:
        """Scan the project and build the dependency graph."""
        nodes: dict[str, dict[str, str | int]] = {}
        node_infos: dict[str, _NodeInfo] = {}
        edges: list[tuple[str, str]] = []

        source_files = self._find_source_files()

        for file_path in source_files:
            rel = str(file_path.relative_to(self.project_root))
            lang = self.EXTENSION_TO_LANG.get(file_path.suffix, "unknown")
            imports = self._extract_imports(file_path, lang)

            info = _NodeInfo(path=rel, language=lang, imports=imports)
            node_infos[rel] = info
            nodes[rel] = {"language": lang, "lines": self._count_lines(file_path)}

        import_map = self._build_import_map(node_infos)

        for rel, info in node_infos.items():
            for imp in info.imports:
                resolved = self._resolve_import(imp, rel, import_map)
                if resolved and resolved != rel:
                    edges.append((rel, resolved))

        return DependencyGraph(nodes=nodes, edges=edges)

    def _find_source_files(self) -> list[Path]:
        """Find all source files in the project."""
        files: list[Path] = []
        for ext in self.EXTENSION_TO_LANG:
            files.extend(self.project_root.rglob(f"*{ext}"))
        return sorted(files)

    def _extract_imports(self, file_path: Path, language: str) -> list[str]:
        """Extract import statements from a file."""
        pattern = self.IMPORT_PATTERNS.get(language)
        if not pattern:
            return []
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return list(set(pattern.findall(text)))
        except OSError:
            return []

    def _build_import_map(self, node_infos: dict[str, _NodeInfo]) -> dict[str, str]:
        """Map simple class names to their file paths."""
        name_to_path: dict[str, str] = {}
        for rel, _info in node_infos.items():
            stem = Path(rel).stem
            name_to_path[stem] = rel
        return name_to_path

    def _resolve_import(self, import_str: str, from_file: str, import_map: dict[str, str]) -> str | None:
        """Resolve an import string to a file path in the project."""
        parts = import_str.replace("/", ".").split(".")
        for part in reversed(parts):
            if part in import_map:
                return import_map[part]
        last = parts[-1] if parts else ""
        if last in import_map:
            return import_map[last]
        return None

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a file."""
        try:
            return sum(1 for _ in file_path.open(encoding="utf-8", errors="replace"))
        except OSError:
            return 0
