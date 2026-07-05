"""Query backends for the interactive knowledge graph service."""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Protocol

from .exporters import to_graphology
from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode
from .stores import JsonKnowledgeGraphStore, LadybugKnowledgeGraphStore

_LOD_KINDS: dict[str, set[str]] = {
    "package": {"package"},
    "file": {"package", "file", "markdown"},
    "symbol": {
        "package",
        "file",
        "markdown",
        "class",
        "constant",
        "enum",
        "function",
        "interface",
        "method",
        "symbol",
    },
    "docs": {"file", "markdown"},
}
_EDGE_KINDS = {"calls", "imports", "extends", "implements", "doc_links", "contains"}
_EXPLORER_EXCLUDE_PREFIXES = (
    "../",
    "..\\",
    ".ast-cache/",
    ".claude/",
    ".codex/",
    ".codegraph/",
    ".git/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "build/",
    "dist/",
    "htmlcov/",
    "node_modules/",
)


class KnowledgeGraphQueryBackend(Protocol):
    """Common query shape used by the local browser service."""

    backend_name: str

    def graph(
        self,
        *,
        lod: str,
        focus: str | None,
        max_nodes: int,
        max_edges: int,
    ) -> dict[str, Any]: ...

    def search(self, query: str, *, limit: int) -> dict[str, Any]: ...

    def files(self, query: str, *, limit: int) -> dict[str, Any]: ...

    def node(self, node_id: str, *, limit: int) -> dict[str, Any]: ...

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int,
        edge_kind: str,
        max_nodes: int,
        max_edges: int,
    ) -> dict[str, Any]: ...


def open_query_backend(project_root: str) -> KnowledgeGraphQueryBackend:
    """Open LadybugDB when present, otherwise fall back to the JSON sidecar."""
    ladybug_store = LadybugKnowledgeGraphStore(project_root)
    if LadybugKnowledgeGraphStore.available() and ladybug_store.exists():
        from .ladybug_query import LadybugKnowledgeGraphQuery

        return LadybugKnowledgeGraphQuery(project_root)
    return JsonKnowledgeGraphQuery(project_root)


class JsonKnowledgeGraphQuery:
    """In-memory JSON sidecar query backend."""

    backend_name = "json"

    def __init__(self, project_root: str) -> None:
        store = JsonKnowledgeGraphStore(project_root)
        if not store.exists():
            raise FileNotFoundError(
                "Knowledge graph sidecar is missing. Run "
                "`tree-sitter-analyzer --knowledge-graph-index` first."
            )
        self.snapshot = _snapshot_from_payload(store.read())
        self.nodes_by_id = {node.id: node for node in self.snapshot.nodes}
        self.edges = list(self.snapshot.edges)
        self.incoming: dict[str, list[KnowledgeEdge]] = {}
        self.outgoing: dict[str, list[KnowledgeEdge]] = {}
        for edge in self.edges:
            self.outgoing.setdefault(edge.source, []).append(edge)
            self.incoming.setdefault(edge.target, []).append(edge)

    def graph(
        self,
        *,
        lod: str,
        focus: str | None,
        max_nodes: int,
        max_edges: int,
    ) -> dict[str, Any]:
        payload = to_graphology(
            self.snapshot,
            lod=lod if lod in _LOD_KINDS else "file",
            focus=focus or None,
            max_nodes=max(1, max_nodes),
            max_edges=max(1, max_edges),
        )
        return _with_backend(payload, self.backend_name)

    def search(self, query: str, *, limit: int) -> dict[str, Any]:
        q = query.strip().lower()
        matches: list[dict[str, Any]] = []
        if q:
            for node in self.snapshot.nodes:
                haystack = " ".join(
                    [node.id, node.label, node.file_path, node.language, node.kind]
                ).lower()
                if q in haystack:
                    matches.append(node.to_dict())
                if len(matches) >= limit:
                    break
        return {"backend": self.backend_name, "query": query, "matches": matches}

    def files(self, query: str, *, limit: int) -> dict[str, Any]:
        q = query.strip().lower()
        all_files = [
            node
            for node in self.snapshot.nodes
            if node.kind in {"file", "markdown"}
            and not _excluded_explorer_path(node.file_path or node.label or node.id)
            and (
                not q
                or q in node.id.lower()
                or q in node.label.lower()
                or q in node.file_path.lower()
            )
        ]
        files = sorted(
            all_files, key=lambda node: node.file_path or node.label or node.id
        )[: max(1, limit)]
        return {
            "backend": self.backend_name,
            "query": query,
            "returned": len(files),
            "total_matches": len(all_files),
            "files": [node.to_dict() for node in files],
        }

    def node(self, node_id: str, *, limit: int) -> dict[str, Any]:
        node = self.nodes_by_id.get(node_id)
        if node is None:
            return {"backend": self.backend_name, "found": False, "id": node_id}
        incoming = self.incoming.get(node_id, [])
        outgoing = self.outgoing.get(node_id, [])
        return {
            "backend": self.backend_name,
            "found": True,
            "node": node.to_dict(),
            "incoming_count": len(incoming),
            "outgoing_count": len(outgoing),
            "incoming": [
                self._edge_with_peer(edge, edge.source) for edge in incoming[:limit]
            ],
            "outgoing": [
                self._edge_with_peer(edge, edge.target) for edge in outgoing[:limit]
            ],
        }

    def neighborhood(
        self,
        node_id: str,
        *,
        depth: int,
        edge_kind: str,
        max_nodes: int,
        max_edges: int,
    ) -> dict[str, Any]:
        if node_id not in self.nodes_by_id:
            return _empty_graph(node_id, self.backend_name)
        allowed_edge_kind = edge_kind if edge_kind in _EDGE_KINDS else "all"
        kept_nodes = self._walk_nodes(
            node_id,
            depth=max(1, min(depth, 6)),
            edge_kind=allowed_edge_kind,
            max_nodes=max(1, max_nodes),
        )
        kept_edges = [
            edge
            for edge in self.edges
            if edge.source in kept_nodes
            and edge.target in kept_nodes
            and (allowed_edge_kind == "all" or edge.kind == allowed_edge_kind)
        ][: max(1, max_edges)]
        snapshot = KnowledgeGraphSnapshot(
            nodes=sorted(
                (self.nodes_by_id[node] for node in kept_nodes), key=lambda n: n.id
            ),
            edges=kept_edges,
            stats={
                **self.snapshot.stats,
                "service_view": "neighborhood",
                "center": node_id,
                "depth": depth,
                "service_node_count": len(kept_nodes),
                "service_edge_count": len(kept_edges),
            },
        )
        return _with_backend(
            to_graphology(
                snapshot,
                lod="symbol",
                max_nodes=max(1, max_nodes),
                max_edges=max(1, max_edges),
            ),
            self.backend_name,
        )

    def _walk_nodes(
        self,
        start: str,
        *,
        depth: int,
        edge_kind: str,
        max_nodes: int,
    ) -> set[str]:
        seen = {start}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue and len(seen) < max_nodes:
            node_id, distance = queue.popleft()
            if distance >= depth:
                continue
            for edge in self.incoming.get(node_id, []) + self.outgoing.get(node_id, []):
                if edge_kind != "all" and edge.kind != edge_kind:
                    continue
                peer = edge.source if edge.target == node_id else edge.target
                if peer in seen or peer not in self.nodes_by_id:
                    continue
                seen.add(peer)
                queue.append((peer, distance + 1))
                if len(seen) >= max_nodes:
                    break
        return seen

    def _edge_with_peer(self, edge: KnowledgeEdge, peer_id: str) -> dict[str, Any]:
        peer = self.nodes_by_id.get(peer_id)
        return {
            **edge.to_dict(),
            "peer": peer.to_dict() if peer else {"id": peer_id, "label": peer_id},
        }


def _snapshot_from_payload(payload: dict[str, Any]) -> KnowledgeGraphSnapshot:
    return KnowledgeGraphSnapshot(
        nodes=[KnowledgeNode(**node) for node in payload.get("nodes", [])],
        edges=[
            KnowledgeEdge(
                id=edge["id"],
                source=edge["source"],
                target=edge["target"],
                kind=edge["kind"],
                line=edge.get("line"),
                provenance=edge.get("provenance", ""),
                metadata=edge.get("metadata") or {},
            )
            for edge in payload.get("edges", [])
        ],
        stats=payload.get("stats", {}),
    )


def _node_from_row(row: dict[str, Any]) -> KnowledgeNode:
    return KnowledgeNode(
        id=str(row["id"]),
        kind=str(row["kind"] or "symbol"),
        label=str(row["label"] or row["id"]),
        file_path=str(row["file_path"] or ""),
        language=str(row["language"] or ""),
        metadata=_json_obj(row.get("metadata_json")),
    )


def _edge_from_row(row: dict[str, Any]) -> KnowledgeEdge:
    return KnowledgeEdge(
        id=str(row["id"]),
        source=str(row["source"]),
        target=str(row["target"]),
        kind=str(row["kind"]),
        line=_nullable_line(row.get("line")),
        provenance=str(row.get("provenance") or ""),
        metadata=_json_obj(row.get("metadata_json")),
    )


def _edge_with_peer_from_row(row: dict[str, Any]) -> dict[str, Any]:
    edge = _edge_from_row(row).to_dict()
    edge["peer"] = KnowledgeNode(
        id=str(row["peer_id"]),
        kind=str(row.get("peer_kind") or "symbol"),
        label=str(row.get("peer_label") or row["peer_id"]),
        file_path=str(row.get("peer_file_path") or ""),
        language=str(row.get("peer_language") or ""),
        metadata=_json_obj(row.get("peer_metadata_json")),
    ).to_dict()
    return edge


def _json_obj(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _nullable_line(raw: Any) -> int | None:
    if raw is None or int(raw) < 0:
        return None
    return int(raw)


def _excluded_explorer_path(path: str) -> bool:
    return path.startswith(_EXPLORER_EXCLUDE_PREFIXES)


def _cypher_list(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def _with_backend(payload: dict[str, Any], backend: str) -> dict[str, Any]:
    payload.setdefault("attributes", {})["backend"] = backend
    payload.setdefault("stats", {})["backend"] = backend
    return payload


def _empty_graph(node_id: str, backend: str) -> dict[str, Any]:
    return {
        "options": {"type": "directed", "multi": True, "allowSelfLoops": True},
        "attributes": {
            "name": "TSA knowledge graph",
            "schema": "tsa.graphology.v1",
            "lod": "symbol",
            "focus": node_id,
            "truncated": False,
            "backend": backend,
        },
        "nodes": [],
        "edges": [],
        "stats": {"export_node_count": 0, "export_edge_count": 0, "backend": backend},
    }
