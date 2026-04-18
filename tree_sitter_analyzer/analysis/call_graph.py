"""Call Graph Analyzer — build function-level call graphs from AST.

Extracts function definitions and call expressions, then builds a directed
call graph showing which functions call which other functions.

Detects:
- Island functions: defined but never called by any other function
- God functions: call more than N other functions (default 20)

Limitations:
- Method dispatch (obj.method()) resolved to method name only
- Dynamic calls (function references, callbacks) not tracked
- Runtime polymorphism not resolved

Supports Python, JavaScript/TypeScript, Java, and Go.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tree_sitter_analyzer.utils import setup_logger
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

if TYPE_CHECKING:
    pass  # tree_sitter type hints only

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_EXT_TO_LANG: dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "language_python"),
    ".js": ("tree_sitter_javascript", "language_javascript"),
    ".jsx": ("tree_sitter_javascript", "language_javascript"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".java": ("tree_sitter_java", "language_java"),
    ".go": ("tree_sitter_go", "language_go"),
}


@dataclass(frozen=True)
class CallEdge:
    """A single call from one function to another."""

    caller: str
    callee: str
    file_path: str
    line: int
    column: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True)
class FunctionDef:
    """A function definition found in the codebase."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    language: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
        }


@dataclass
class CallGraphResult:
    """Aggregated call graph analysis result."""

    file_path: str
    functions: tuple[FunctionDef, ...] = ()
    call_edges: tuple[CallEdge, ...] = ()
    island_functions: tuple[str, ...] = ()
    god_functions: tuple[tuple[str, int], ...] = ()

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def edge_count(self) -> int:
        return len(self.call_edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "function_count": self.function_count,
            "edge_count": self.edge_count,
            "island_count": len(self.island_functions),
            "god_count": len(self.god_functions),
            "functions": [f.to_dict() for f in self.functions],
            "call_edges": [e.to_dict() for e in self.call_edges],
            "island_functions": list(self.island_functions),
            "god_functions": [
                {"function": name, "callee_count": count}
                for name, count in self.god_functions
            ],
        }


_FUNC_DEF_QUERIES: dict[str, str] = {
    "python": "(function_definition name: (identifier) @func_name) @func_def",
    "javascript": " ".join([
        "(function_declaration name: (identifier) @func_name) @func_def",
        "(method_definition name: (property_identifier) @func_name) @func_def",
    ]),
    "typescript": " ".join([
        "(function_declaration name: (identifier) @func_name) @func_def",
        "(method_definition name: (property_identifier) @func_name) @func_def",
    ]),
    "tsx": " ".join([
        "(function_declaration name: (identifier) @func_name) @func_def",
        "(method_definition name: (property_identifier) @func_name) @func_def",
    ]),
    "java": " ".join([
        "(method_declaration name: (identifier) @func_name) @func_def",
        "(constructor_declaration) @func_def",
    ]),
    "go": " ".join([
        "(function_declaration name: (identifier) @func_name) @func_def",
        "(method_declaration name: (field_identifier) @func_name) @func_def",
    ]),
}

_CALL_QUERIES: dict[str, str] = {
    "python": "(call function: (identifier) @callee) @call",
    "javascript": "(call_expression function: (identifier) @callee) @call",
    "typescript": "(call_expression function: (identifier) @callee) @call",
    "tsx": "(call_expression function: (identifier) @callee) @call",
    "java": "(method_invocation name: (identifier) @callee) @call",
    "go": "(call_expression function: (identifier) @callee) @call",
}

_METHOD_CALL_QUERIES: dict[str, str] = {
    "python": "(call function: (attribute attribute: (identifier) @callee)) @call",
    "java": "(method_invocation object: (identifier) name: (identifier) @callee) @call",
    "go": "(call_expression function: (selector_expression field: (field_identifier) @callee)) @call",
}

_FUNC_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition"},
    "typescript": {"function_declaration", "method_definition"},
    "tsx": {"function_declaration", "method_definition"},
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
}


def _detect_language(file_path: str) -> str | None:
    """Detect language from file extension."""
    ext = Path(file_path).suffix
    if ext not in _EXT_TO_LANG:
        return None
    _, lang_func = _EXT_TO_LANG[ext]
    return lang_func.replace("language_", "")


def _node_text(node: Any) -> str:
    """Extract text from a tree-sitter node."""
    raw = node.text
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)


class CallGraphAnalyzer:
    """Analyze function call graphs in source code."""

    def __init__(self, language_name: str = "python") -> None:
        self.language_name = language_name
        self._language: Any = None
        self._parser: Any = None
        self._load_language(language_name)

    def _load_language(self, language_name: str) -> None:
        """Load tree-sitter language and parser."""
        import tree_sitter

        lang_map: dict[str, tuple[str, str]] = {
            "python": ("tree_sitter_python", "language"),
            "javascript": ("tree_sitter_javascript", "language"),
            "typescript": ("tree_sitter_typescript", "language_typescript"),
            "tsx": ("tree_sitter_typescript", "language_tsx"),
            "java": ("tree_sitter_java", "language"),
            "go": ("tree_sitter_go", "language"),
        }
        entry = lang_map.get(language_name)
        if entry is None:
            logger.warning("Unsupported language: %s", language_name)
            return
        module_name, func_name = entry
        mod = __import__(module_name)
        func = getattr(mod, func_name)
        self._language = tree_sitter.Language(func())
        self._parser = tree_sitter.Parser(self._language)

    def analyze_file(
        self,
        file_path: str,
        god_threshold: int = 20,
    ) -> CallGraphResult:
        """Analyze a single file for call graph."""
        if self._parser is None:
            return CallGraphResult(file_path=file_path)

        path = Path(file_path)
        if not path.exists():
            return CallGraphResult(file_path=file_path)

        source = path.read_bytes()
        tree = self._parser.parse(source)

        functions = self._extract_functions(tree, file_path)
        call_edges = self._extract_calls(tree, file_path)
        island_functions = self._find_islands(functions, call_edges)
        god_functions = self._find_god_functions(call_edges, god_threshold)

        return CallGraphResult(
            file_path=file_path,
            functions=tuple(functions),
            call_edges=tuple(call_edges),
            island_functions=tuple(island_functions),
            god_functions=tuple(god_functions),
        )

    def analyze_directory(
        self,
        dir_path: str,
        god_threshold: int = 20,
    ) -> list[CallGraphResult]:
        """Analyze all supported files in a directory."""
        results: list[CallGraphResult] = []
        root = Path(dir_path)

        for ext in SUPPORTED_EXTENSIONS:
            for path in sorted(root.rglob(f"*{ext}")):
                lang = _detect_language(str(path))
                if lang is None:
                    continue
                if lang != self.language_name:
                    continue
                result = self.analyze_file(str(path), god_threshold)
                results.append(result)

        return results

    def _extract_functions(
        self, tree: Any, file_path: str,
    ) -> list[FunctionDef]:
        """Extract function definitions from AST."""
        if self.language_name not in _FUNC_DEF_QUERIES:
            return []

        query_str = _FUNC_DEF_QUERIES[self.language_name]
        matches = TreeSitterQueryCompat.execute_query(
            self._language, query_str, tree.root_node,
        )

        functions: list[FunctionDef] = []
        seen: set[str] = set()

        # Group captures by position to reconstruct function nodes.
        func_nodes: dict[tuple[int, int], tuple[Any, str | None]] = {}

        for node, capture_name in matches:
            if capture_name == "func_def":
                key = (node.start_point[0], node.start_point[1])
                existing = func_nodes.get(key)
                if existing is None:
                    func_nodes[key] = (node, None)
                # func_def node recorded, name may come from a separate capture
            elif capture_name == "func_name":
                # Find the parent func_def node.
                parent = node.parent
                if parent is not None:
                    key = (parent.start_point[0], parent.start_point[1])
                    existing = func_nodes.get(key)
                    if existing is not None:
                        func_nodes[key] = (existing[0], _node_text(node))
                    else:
                        func_nodes[key] = (parent, _node_text(node))

        for key, (func_node, name) in func_nodes.items():
            func_name = name if name is not None else "<constructor>"
            dup_key = f"{func_name}:{key[0]}"
            if dup_key in seen:
                continue
            seen.add(dup_key)

            functions.append(FunctionDef(
                name=func_name,
                file_path=file_path,
                start_line=func_node.start_point[0] + 1,
                end_line=func_node.end_point[0] + 1,
                language=self.language_name,
            ))

        return functions

    def _extract_calls(
        self, tree: Any, file_path: str,
    ) -> list[CallEdge]:
        """Extract call expressions from AST."""
        if self._parser is None:
            return []

        call_edges: list[CallEdge] = []

        for query_dict in (_CALL_QUERIES, _METHOD_CALL_QUERIES):
            query_str = query_dict.get(self.language_name)
            if query_str is None:
                continue

            matches = TreeSitterQueryCompat.execute_query(
                self._language, query_str, tree.root_node,
            )

            call_node: Any = None
            callee_name: str | None = None

            for node, capture_name in matches:
                if capture_name == "call":
                    call_node = node
                elif capture_name == "callee":
                    callee_name = _node_text(node)

                if call_node is not None and callee_name is not None:
                    caller_name = self._find_enclosing_function(call_node)
                    if caller_name is None:
                        caller_name = "<module>"

                    call_edges.append(CallEdge(
                        caller=caller_name,
                        callee=callee_name,
                        file_path=file_path,
                        line=call_node.start_point[0] + 1,
                        column=call_node.start_point[1],
                    ))
                    call_node = None
                    callee_name = None

        return call_edges

    def _find_enclosing_function(self, node: Any) -> str | None:
        """Walk up the tree to find the enclosing function definition."""
        current = node.parent
        types = _FUNC_NODE_TYPES.get(self.language_name, set())

        while current is not None:
            if current.type in types:
                name_node = current.child_by_field_name("name")
                if name_node is not None:
                    return _node_text(name_node)
                return "<anonymous>"
            current = current.parent
        return None

    def _find_islands(
        self,
        functions: list[FunctionDef],
        call_edges: list[CallEdge],
    ) -> list[str]:
        """Find functions that are never called by any other function or module."""
        called_names: set[str] = set()
        for edge in call_edges:
            called_names.add(edge.callee)

        islands: list[str] = []
        for func in functions:
            if func.name not in called_names:
                islands.append(func.name)

        return islands

    def _find_god_functions(
        self,
        call_edges: list[CallEdge],
        threshold: int,
    ) -> list[tuple[str, int]]:
        """Find functions that call more than N distinct other functions."""
        callee_sets: dict[str, set[str]] = defaultdict(set)
        for edge in call_edges:
            if edge.caller != "<module>":
                callee_sets[edge.caller].add(edge.callee)

        god_functions: list[tuple[str, int]] = []
        for func_name, callees in callee_sets.items():
            if len(callees) >= threshold:
                god_functions.append((func_name, len(callees)))

        return sorted(god_functions, key=lambda x: x[1], reverse=True)
