"""LadybugDB query backend for the interactive knowledge graph service."""

from __future__ import annotations

from collections import deque
from typing import Any

from .exporters import to_graphology
from .models import KnowledgeEdge, KnowledgeGraphSnapshot, KnowledgeNode
from .query import (
    _EDGE_KINDS,
    _EXPLORER_EXCLUDE_PREFIXES,
    _LOD_KINDS,
    _cypher_list,
    _edge_from_row,
    _edge_with_peer_from_row,
    _empty_graph,
    _node_from_row,
    _with_backend,
)
from .stores import LadybugKnowledgeGraphStore


class LadybugKnowledgeGraphQuery:
    """LadybugDB-backed query backend for graph traversal."""

    backend_name = "ladybug"

    def __init__(self, project_root: str) -> None:
        lb = LadybugKnowledgeGraphStore._import_ladybug()
        store = LadybugKnowledgeGraphStore(project_root)
        if not store.exists():
            raise FileNotFoundError(
                "LadybugDB graph mirror is missing. Run "
                "`tree-sitter-analyzer --knowledge-graph-index "
                "--knowledge-graph-backend auto` first."
            )
        self.db = lb.Database(store.path, read_only=True)
        self.conn = lb.Connection(self.db)

    def graph(
        self,
        *,
        lod: str,
        focus: str | None,
        max_nodes: int,
        max_edges: int,
    ) -> dict[str, Any]:
        allowed = sorted(_LOD_KINDS.get(lod, _LOD_KINDS["file"]))
        where = "n.kind IN " + _cypher_list(allowed)
        if focus:
            where += (
                " AND (n.id CONTAINS $focus OR n.label CONTAINS $focus "
                "OR n.file_path CONTAINS $focus)"
            )
        nodes = self._nodes(
            f"MATCH (n:KGNode) WHERE {where} "
            "RETURN n.id AS id, n.kind AS kind, n.label AS label, "
            "n.file_path AS file_path, n.language AS language, "
            "n.metadata_json AS metadata_json ORDER BY n.id LIMIT $limit",
            {"focus": focus or "", "limit": max(1, max_nodes)},
        )
        node_ids = {node.id for node in nodes}
        edges = self._edges_between(node_ids, max_edges=max(1, max_edges))
        snapshot = KnowledgeGraphSnapshot(
            nodes=nodes,
            edges=edges,
            stats={
                **self._stats(),
                "service_view": "overview",
                "service_node_count": len(nodes),
                "service_edge_count": len(edges),
            },
        )
        return _with_backend(
            to_graphology(
                snapshot, lod="symbol", max_nodes=max_nodes, max_edges=max_edges
            ),
            self.backend_name,
        )

    def search(self, query: str, *, limit: int) -> dict[str, Any]:
        q = query.strip()
        nodes = (
            self._nodes(
                "MATCH (n:KGNode) WHERE n.id CONTAINS $q OR n.label CONTAINS $q "
                "OR n.file_path CONTAINS $q OR n.kind CONTAINS $q "
                "RETURN n.id AS id, n.kind AS kind, n.label AS label, "
                "n.file_path AS file_path, n.language AS language, "
                "n.metadata_json AS metadata_json ORDER BY n.id LIMIT $limit",
                {"q": q, "limit": max(1, limit)},
            )
            if q
            else []
        )
        return {
            "backend": self.backend_name,
            "query": query,
            "matches": [node.to_dict() for node in nodes],
        }

    def files(self, query: str, *, limit: int) -> dict[str, Any]:
        q = query.strip()
        exclude_prefixes = " AND ".join(
            f"NOT n.file_path STARTS WITH {prefix!r}"
            for prefix in _EXPLORER_EXCLUDE_PREFIXES
            if "\\" not in prefix
        )
        where = f"n.kind IN ['file', 'markdown'] AND {exclude_prefixes}"
        if q:
            where += (
                " AND (n.id CONTAINS $q OR n.label CONTAINS $q "
                "OR n.file_path CONTAINS $q)"
            )
        nodes = self._nodes(
            f"MATCH (n:KGNode) WHERE {where} "
            "RETURN n.id AS id, n.kind AS kind, n.label AS label, "
            "n.file_path AS file_path, n.language AS language, "
            "n.metadata_json AS metadata_json ORDER BY n.file_path, n.id LIMIT $limit",
            {"q": q, "limit": max(1, limit)},
        )
        total_rows = self._rows(
            f"MATCH (n:KGNode) WHERE {where} RETURN count(n) AS total",
            {"q": q},
        )
        return {
            "backend": self.backend_name,
            "query": query,
            "returned": len(nodes),
            "total_matches": int(total_rows[0]["total"]) if total_rows else len(nodes),
            "files": [node.to_dict() for node in nodes],
        }

    def node(self, node_id: str, *, limit: int) -> dict[str, Any]:
        nodes = self._nodes(
            "MATCH (n:KGNode) WHERE n.id = $id RETURN n.id AS id, "
            "n.kind AS kind, n.label AS label, n.file_path AS file_path, "
            "n.language AS language, n.metadata_json AS metadata_json LIMIT 1",
            {"id": node_id},
        )
        if not nodes:
            return {"backend": self.backend_name, "found": False, "id": node_id}
        return {
            "backend": self.backend_name,
            "found": True,
            "node": nodes[0].to_dict(),
            "incoming_count": self._edge_count(node_id, "incoming"),
            "outgoing_count": self._edge_count(node_id, "outgoing"),
            "incoming": self._incident_edges(node_id, "incoming", limit),
            "outgoing": self._incident_edges(node_id, "outgoing", limit),
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
        if not self.node(node_id, limit=1)["found"]:
            return _empty_graph(node_id, self.backend_name)
        kept = self._walk_nodes(
            node_id,
            depth=max(1, min(depth, 6)),
            edge_kind=edge_kind if edge_kind in _EDGE_KINDS else "all",
            max_nodes=max(1, max_nodes),
        )
        nodes = self._nodes_by_ids(kept)
        edges = self._edges_between(kept, max_edges=max(1, max_edges))
        snapshot = KnowledgeGraphSnapshot(
            nodes=nodes,
            edges=edges,
            stats={
                **self._stats(),
                "service_view": "neighborhood",
                "center": node_id,
                "depth": depth,
                "service_node_count": len(nodes),
                "service_edge_count": len(edges),
            },
        )
        return _with_backend(
            to_graphology(
                snapshot, lod="symbol", max_nodes=max_nodes, max_edges=max_edges
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
            for peer in self._peer_ids(node_id, edge_kind=edge_kind):
                if peer in seen:
                    continue
                seen.add(peer)
                queue.append((peer, distance + 1))
                if len(seen) >= max_nodes:
                    break
        return seen

    def _peer_ids(self, node_id: str, *, edge_kind: str) -> list[str]:
        condition = "" if edge_kind == "all" else " AND e.kind = $kind"
        rows = self._rows(
            "MATCH (s:KGNode)-[e:KGEdge]->(t:KGNode) "
            "WHERE (s.id = $id OR t.id = $id)"
            + condition
            + " RETURN s.id AS source, t.id AS target LIMIT 500",
            {"id": node_id, "kind": edge_kind},
        )
        return [
            row["target"] if row["source"] == node_id else row["source"] for row in rows
        ]

    def _incident_edges(
        self,
        node_id: str,
        direction: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if direction == "incoming":
            query = (
                "MATCH (p:KGNode)-[e:KGEdge]->(n:KGNode) WHERE n.id = $id "
                "RETURN e.id AS id, p.id AS source, n.id AS target, "
                "e.kind AS kind, e.line AS line, e.provenance AS provenance, "
                "e.metadata_json AS metadata_json, p.id AS peer_id, "
                "p.kind AS peer_kind, p.label AS peer_label, "
                "p.file_path AS peer_file_path, p.language AS peer_language, "
                "p.metadata_json AS peer_metadata_json LIMIT $limit"
            )
        else:
            query = (
                "MATCH (n:KGNode)-[e:KGEdge]->(p:KGNode) WHERE n.id = $id "
                "RETURN e.id AS id, n.id AS source, p.id AS target, "
                "e.kind AS kind, e.line AS line, e.provenance AS provenance, "
                "e.metadata_json AS metadata_json, p.id AS peer_id, "
                "p.kind AS peer_kind, p.label AS peer_label, "
                "p.file_path AS peer_file_path, p.language AS peer_language, "
                "p.metadata_json AS peer_metadata_json LIMIT $limit"
            )
        rows = self._rows(query, {"id": node_id, "limit": max(1, limit)})
        return [_edge_with_peer_from_row(row) for row in rows]

    def _edge_count(self, node_id: str, direction: str) -> int:
        if direction == "incoming":
            query = (
                "MATCH (:KGNode)-[e:KGEdge]->(n:KGNode) "
                "WHERE n.id = $id RETURN count(e) AS total"
            )
        else:
            query = (
                "MATCH (n:KGNode)-[e:KGEdge]->(:KGNode) "
                "WHERE n.id = $id RETURN count(e) AS total"
            )
        rows = self._rows(query, {"id": node_id})
        return int(rows[0]["total"]) if rows else 0

    def _nodes_by_ids(self, node_ids: set[str]) -> list[KnowledgeNode]:
        nodes = [self._node_from_id(node_id) for node_id in node_ids]
        return sorted((node for node in nodes if node is not None), key=lambda n: n.id)

    def _node_from_id(self, node_id: str) -> KnowledgeNode | None:
        nodes = self._nodes(
            "MATCH (n:KGNode) WHERE n.id = $id RETURN n.id AS id, "
            "n.kind AS kind, n.label AS label, n.file_path AS file_path, "
            "n.language AS language, n.metadata_json AS metadata_json LIMIT 1",
            {"id": node_id},
        )
        return nodes[0] if nodes else None

    def _edges_between(
        self,
        node_ids: set[str],
        *,
        max_edges: int,
    ) -> list[KnowledgeEdge]:
        if not node_ids:
            return []
        rows = self._rows(
            "MATCH (s:KGNode)-[e:KGEdge]->(t:KGNode) "
            "WHERE s.id IN "
            + _cypher_list(sorted(node_ids))
            + " AND t.id IN "
            + _cypher_list(sorted(node_ids))
            + " RETURN e.id AS id, s.id AS source, t.id AS target, "
            "e.kind AS kind, e.line AS line, e.provenance AS provenance, "
            "e.metadata_json AS metadata_json LIMIT $limit",
            {"limit": max(1, max_edges)},
        )
        return [_edge_from_row(row) for row in rows]

    def _nodes(self, query: str, params: dict[str, Any]) -> list[KnowledgeNode]:
        return [_node_from_row(row) for row in self._rows(query, params)]

    def _stats(self) -> dict[str, Any]:
        node_rows = self._rows("MATCH (n:KGNode) RETURN count(n) AS total", {})
        edge_rows = self._rows("MATCH ()-[e:KGEdge]->() RETURN count(e) AS total", {})
        return {
            "node_count": int(node_rows[0]["total"]) if node_rows else 0,
            "edge_count": int(edge_rows[0]["total"]) if edge_rows else 0,
        }

    def _rows(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = self.conn.execute(query, params)
        columns = result.get_column_names()
        return [dict(zip(columns, values, strict=True)) for values in result.get_all()]
