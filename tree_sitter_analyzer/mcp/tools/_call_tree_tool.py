#!/usr/bin/env python3
"""``callee_tree`` / ``caller_tree`` MCP tools — the *tree primitive*.

One call returns a depth-limited NESTED call tree so an agent does not have to
iterate ``codegraph_callees`` / ``codegraph_callers`` BFS-style across many
round-trips. Mirrors mycelium RFC-0020 (callee tree) / RFC-0021 (caller tree).

Both tools reuse the existing single-hop call-graph machinery:

* SQL fast path: ``ASTCache.query_callees`` / ``query_callers`` with
  ``max_depth=1`` per hop (B1 unified ``edges`` table via ``bfs_callees`` /
  ``bfs_callers``).
* Graph fallback: ``CallGraph.callees_of`` / ``callers_of`` when no SQL edge
  cache exists yet.

The nested DFS, depth cap, global node cap, and cycle guard live in the pure
``_call_tree.build_call_tree`` helper. These tools only adapt the storage layer
into the storage-agnostic ``expand`` callback and wrap the result in the
standard response envelope (with TOON support and a deterrent ``next_step``).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from ...utils import setup_logger
from . import _call_tree
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .codegraph_relation_tool import CodeGraphRelationToolMixin

logger = setup_logger(__name__)

_CALLEE_DETERRENT = (
    "Full callee tree to depth {depth} returned ({count} nodes). Answer from "
    "this tree — no further codegraph_callees / get_callees / Read calls "
    "needed for these functions."
)
_CALLER_DETERRENT = (
    "Full caller tree to depth {depth} returned ({count} nodes). Answer from "
    "this tree — no further codegraph_callers / get_callers / Read calls "
    "needed for these functions."
)

_TRUNCATION_HINT = (
    " Tree was truncated at the node cap; narrow with file_path or lower "
    "max_depth for the unexpanded branches."
)


def _normalize_callee(edge: dict[str, Any]) -> dict[str, Any]:
    """SQL callee edge / graph callee dict → uniform {name,file,line}."""
    name = edge.get("callee_name") or edge.get("name") or ""
    file = (
        edge.get("callee_resolved_file")
        or edge.get("callee_file")
        or edge.get("file")
        or ""
    )
    line = edge.get("callee_line", edge.get("line", 0))
    return {"name": name, "file": file, "line": int(line or 0)}


def _normalize_caller(edge: dict[str, Any]) -> dict[str, Any]:
    """SQL caller edge / graph caller dict → uniform {name,file,line}."""
    name = edge.get("caller_name") or edge.get("name") or ""
    file = edge.get("caller_file") or edge.get("file") or ""
    line = edge.get("caller_line", edge.get("line", 0))
    return {"name": name, "file": file, "line": int(line or 0)}


class _CallTreeBase(CodeGraphRelationToolMixin, BaseMCPTool):
    """Shared execution for callee/caller tree tools."""

    # Subclasses set these.
    _tool_name: str = ""
    _direction: str = ""  # "callees" | "callers"
    _deterrent: str = ""

    def __init__(self, project_root: str | None = None) -> None:
        self._init_relation_state()
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._reset_relation_state()

    def get_tool_definition(self) -> dict[str, Any]:
        verb = "calls" if self._direction == "callees" else "is called by"
        return {
            "name": self._tool_name,
            "description": (
                f"Depth-limited NESTED {self._direction[:-1]} tree in ONE call. "
                f"Returns the whole tree of what a function transitively {verb} "
                "(up to max_depth) so you do NOT have to iterate "
                f"codegraph_{self._direction} per node. "
                "Each node: {name, file, line, children}. Capped to protect the "
                "token budget on large graphs."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Root function/method name to build the tree from",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate the root symbol",
                },
                "max_depth": {
                    "type": "integer",
                    "description": (
                        "Maximum tree depth (1 = direct neighbours only). "
                        f"Default {_call_tree.DEFAULT_MAX_DEPTH}, "
                        f"capped at {_call_tree.MAX_DEPTH_CAP}."
                    ),
                    "default": _call_tree.DEFAULT_MAX_DEPTH,
                },
                "max_nodes": {
                    "type": "integer",
                    "description": (
                        "Global cap on total tree nodes (truncation guard for "
                        f"large graphs). Default {_call_tree.DEFAULT_MAX_NODES}."
                    ),
                    "default": _call_tree.DEFAULT_MAX_NODES,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        # ``symbol`` is the public name; ``function_name`` accepted as an alias
        # so callers using the callers/callees vocabulary don't trip the guard.
        if not (arguments.get("symbol") or arguments.get("function_name")):
            raise ValueError("symbol is required")
        return True

    def _make_expander(self) -> _call_tree.Expander:
        """Return a storage-agnostic single-hop expand(name, file) callback."""
        cache = self._try_get_cache()
        use_sql = cache is not None and cache.has_call_edges()
        # Build the graph fallback eagerly only when SQL edges are absent, so
        # the closure never has to deal with a ``None`` graph.
        graph = None if use_sql else self._get_call_graph()

        if self._direction == "callees":

            def expand(name: str, file: str | None) -> list[dict[str, Any]]:
                if use_sql:
                    rows = cache.query_callees(name, caller_file=file, max_depth=1)
                else:
                    assert graph is not None  # nosec B101 — guarded by use_sql
                    rows = graph.callees_of(name, file)
                return list(_dedup_nodes(_normalize_callee(r) for r in rows))

        else:

            def expand(name: str, file: str | None) -> list[dict[str, Any]]:
                if use_sql:
                    rows = cache.query_callers(name, callee_file=file, max_depth=1)
                else:
                    assert graph is not None  # nosec B101 — guarded by use_sql
                    rows = graph.callers_of(name, file)
                return list(_dedup_nodes(_normalize_caller(r) for r in rows))

        return expand

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        symbol = str(arguments.get("symbol") or arguments.get("function_name") or "")
        file_path = arguments.get("file_path")
        max_depth = int(arguments.get("max_depth", _call_tree.DEFAULT_MAX_DEPTH))
        max_nodes = int(arguments.get("max_nodes", _call_tree.DEFAULT_MAX_NODES))
        output_format = arguments.get("output_format", "toon")

        expand = self._make_expander()
        tree = _call_tree.build_call_tree(
            symbol,
            file_path,
            expand,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )

        found = bool(tree["root"]["children"])
        deterrent = self._deterrent.format(
            depth=tree["max_depth"], count=tree["node_count"]
        )
        if tree["truncated"]:
            deterrent += _TRUNCATION_HINT

        result = build_response(
            verdict="INFO" if found else "NOT_FOUND",
            data_source=self._data_source,
            symbol=symbol,
            node_count=tree["node_count"],
            truncated=tree["truncated"],
            tree=tree,
        )
        result["next_step"] = deterrent

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


def _dedup_nodes(
    nodes: Iterable[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Drop empty-name rows and dedup by (file, name) preserving order."""
    seen: set[str] = set()
    for n in nodes:
        if not n["name"]:
            continue
        key = f"{n['file']}:{n['name']}"
        if key in seen:
            continue
        seen.add(key)
        yield n


class CodeGraphCalleeTreeTool(_CallTreeBase):
    """One-call depth-limited NESTED callee tree (mycelium RFC-0020 parity)."""

    _tool_name = "codegraph_callee_tree"
    _direction = "callees"
    _deterrent = _CALLEE_DETERRENT


class CodeGraphCallerTreeTool(_CallTreeBase):
    """One-call depth-limited NESTED caller tree (mycelium RFC-0021 parity)."""

    _tool_name = "codegraph_caller_tree"
    _direction = "callers"
    _deterrent = _CALLER_DETERRENT
